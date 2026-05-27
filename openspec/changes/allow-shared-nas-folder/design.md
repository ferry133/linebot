## Context

`projects.nas_path` 在 schema 上沒有 UNIQUE 約束，但 UI 與 `/api/nas/folders?unassigned=1` 把它當成 1:1 處理：匯入 dialog 只列出未被引用的資料夾，且匯入時強制 `case_number = 資料夾名`（因 `case_number` UNIQUE）。當實務上要把同一案場分成多個 Trello board 管理時，第二個 project 就無法建立。

封存連動會 `os.rename` 把資料夾從 `00. 執行中案場/` 搬到 `archived/`；一旦允許共用，搬移時機必須改用「引用計數」邏輯，否則會把仍在用的資料夾搬走。

## Goals / Non-Goals

**Goals:**
- 同一 NAS 資料夾可對應多個 `projects` 記錄
- 匯入 dialog 顯示所有資料夾，並可獨立輸入案號
- 封存/還原時不破壞其他仍引用此資料夾的 active project

**Non-Goals:**
- 不引入專屬的「案場 (site)」實體層；維持 `projects.nas_path` 為字串路徑
- 不為 `nas_path` 加 UNIQUE 約束、也不加 FK
- 不改變 RBAC / 通知行為（皆以 `project_id` / `board_id` 為基礎）

## Decisions

**D1. 不引入新的 `sites` 實體**
- 走最小改動：把 1:1 限制當成偶然限制移除即可
- 理由：目前 NAS 路徑就是字串，沒有需求要查「同一案場下所有 project」；引入新表會帶來 migration 與 admin UI 大改

**D2. 匯入 dialog 新增「案號」欄位（選填）**
- 留空 → 後端 `_generate_case_number(year)` auto-gen
- 有填 → 用使用者輸入（unique 由 DB 約束）
- 替代方案：強制 auto-gen — 否決，因現行也允許自訂如 `115-001-XX公館`

**D3. NAS 搬移用引用計數判斷**
- PUT `/api/projects/<id>` 切到 `archived` 時：
  - `SELECT COUNT(*) FROM projects WHERE nas_path = %s AND status != 'archived' AND project_id != %s`
  - 若 > 0 → 不搬資料夾，僅更新 DB；回應加上 `nas_warning: "folder still in use by other active projects"`
  - 若 = 0 → 照舊 `_archive_nas_folder`
- 還原（`archived → active`）對稱：
  - 若資料夾已在 `archived/` 下 → 搬回 `00. 執行中案場/`
  - 若資料夾已在 `00. 執行中案場/`（因其他 project 還在用而未搬）→ 跳過搬移，僅改 DB 狀態與 `nas_path`
- 同時要更新其他相同 `nas_path` 紀錄的字串嗎？— **不更新**，DB 只記專案自身狀態；搬移成功時把該專案的 `nas_path` 改成新位置即可（但因現在會 skip，正常情況都不會走到 update path）

**D4. `case_number` 仍 UNIQUE**
- 不放寬，避免破壞既有 RBAC log 與報表辨識
- 共用資料夾下兩個 project 必須有不同案號

## Risks / Trade-offs

- [使用者誤以為「封存」會搬資料夾，結果未搬] → API 回 `nas_warning`，前端在儲存後 alert 顯示「資料夾仍被 X 個 active 專案引用，未搬移」
- [DB 中相同 `nas_path` 字串若有 trailing slash 等差異，引用計數會 miss] → POST 時統一以 `os.path.normpath` 寫入；計數比較直接字串相等
- [還原時資料夾位置混亂（部分在 archived/，部分在 active）] → 還原邏輯先檢查實體位置；若不在預期位置且找不到對應實體則回 400 並提示手動處理

## Migration Plan

- 無 schema 變更
- 部署順序：admin 先 rollout（讀取 unfiltered folders + 新案號欄）；其他 agent 不受影響
- Rollback：revert admin image tag 即可
