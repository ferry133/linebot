## Context

目前「專案」概念分散在三處：`line_users.projects`（JSONB 字串陣列）、`trello_boards`（board name/id 映射）、NAS 資料夾（無 DB 記錄）。三者之間靠 board name 字串做 loose join，無穩定 ID。

系統需要一個 `projects` 表作為全局 correlation 中心，讓 user、Trello board、NAS 資料夾都能以 `project_id` 為 anchor 互相連結。

NAS 已透過 NFS export（`10.9.1.12:/volume2/jia.homedesign`）對 jgu5 cluster 開放，資料夾已有 15 個實際案場，結構已成熟（15 個子資料夾標準化）。

## Goals / Non-Goals

**Goals:**
- 建立 `projects` 表與 `line_user_projects` 關聯表
- 案號自動生成（民國年 + 當年流水號）
- Admin UI 專案管理頁（CRUD + user assignment）
- 建立專案時 NAS copytree，路徑寫回 DB
- 通知收件人解析改為走 project_id 路徑
- 歷史案可手動建 record（Trello board 可 null）

**Non-Goals:**
- 付款/發票資訊進 DB（維持純 NAS）
- 相簿相片系統（維持 NAS）
- NAS 檔案的 CRUD 操作（只做建立，不做後續管理）
- 通知邏輯的根本重構（掃描 Trello 的方式不變）

## Decisions

### D1：`projects.project_id` 用 UUID 而非自增整數

UUID 在多環境（dev/staging/prod）不會衝突，適合未來可能的多 workspace 擴展。案號（`115年第3案`）為顯示用欄位，與 PK 分離。

### D2：`line_user_projects.relation` 欄位取代在 `line_users.role` 裡隱含的關係

一個 user 可以是某專案的 `customer`，同時是另一個專案的 `vendor`（例如廠商也是回頭客）。relation 放在關聯表而非 user 表，才能正確表達此多對多語意。

### D3：NAS 操作用 `shutil.copytree`（pod 掛載後），不用 NAS HTTP API

Synology DSM API 需要 session token，額外複雜度不值得。NFS mount 後直接 `shutil.copytree` 更簡單可靠。template 資料夾約定放在 `_template_new_project/`（底線開頭，不混入案場清單）。

備選：Synology DSM API → 排除，因需維護 session/token 邏輯。

### D7：NFS 掛載方式——HelmRelease `type: nfs`，不用 PVC

`sc-nas` StorageClass 使用 nfs-subdir provisioner，會在 NAS 下自動建 sub-directory（格式 `{cluster}-{namespace}-{pvc-name}`），無法掛載現有的 `jia.homedesign` 目錄結構。

改為在 HelmRelease 的 `persistence` 區段直接宣告 `type: nfs`，與 jg-base 的 `claude-code` helmrelease 相同做法：
```yaml
persistence:
  jia-homedesign:
    type: nfs
    server: "${NAS_SERVER}"
    path: "/volume2/jia.homedesign"
    globalMounts:
      - path: /mnt/nas/jia.homedesign
```

此方式直接掛現有目錄，無需建立 PV/PVC manifest。

### D4：現有 JSONB 資料遷移策略——migration script 在 apply 時執行

migration `004_projects.sql` 建表後，`005_migrate_projects.sql` 將 `line_users.projects` JSONB 陣列中的每個 board name：
1. 在 `trello_boards` 查對應 `board_id`
2. 在 `projects` 建立 record（`nas_path` 暫 null，`status=active`）
3. 在 `line_user_projects` 建立 relation=`customer`（保守預設）
4. 無法找到 board_id 的孤兒 board name：建 project record 但 `trello_board_id=null`，人工事後補填

`line_users.projects` 欄位保留但不再讀寫（廢棄，未來版本再 DROP）。

### D5：Admin UI 新增「Projects」分頁，user 編輯的 project 選擇器改為從 `/api/projects` 拉清單

不再從 `/api/boards` 拉 board name，改從 `/api/projects` 拉 project 實體（含 project_id、display name、案號）。UI 呈現：`{案號} {名稱}`。

### D6：通知收件人解析

`trello_line_notifier.py` 中，原本的 board_name 掃描改為：
```
board_id（Trello 回傳）
  → SELECT project_id FROM projects WHERE trello_board_id = board_id
  → SELECT line_id FROM line_user_projects WHERE project_id = ? AND relation IN ('customer', 'vendor')
  → 推播
```

## Risks / Trade-offs

- **NFS mount 失敗**：pod 啟動失敗。Mitigation：NAS 操作包在 try/except，失敗時 log + 繼續（专案 record 仍建立，nas_path 留 null，事後手動補）。
- **template 資料夾不存在**：copytree 拋例外。Mitigation：建立前檢查 template 路徑，若不存在則跳過 NAS 步驟並警告。
- **JSONB 遷移中 board name 找不到對應**：孤兒 record。Mitigation：migration script 輸出 WARNING log，人工事後補填 trello_board_id。
- **admin_server.py 單檔肥大**：目前已含大量 inline HTML。新增 projects 管理頁會讓檔案更大。這是既有技術債，本 change 不解決。

## Migration Plan

1. 套用 `migrations/004_projects.sql`（建表）
2. 套用 `migrations/005_migrate_projects.sql`（遷移 JSONB 資料）
3. k8s：在 linebot HelmRelease 加入 `type: nfs` persistence 區段（參考 jg-base claude-code 模式）
4. build & push image，rollout restart
5. Admin UI 確認 projects 頁正常
6. 驗證通知收件人解析走新路徑

Rollback：`line_users.projects` JSONB 欄位未 DROP，舊程式碼可直接切回。

## Open Questions

- template 資料夾由 user 手動建立（`/volume2/jia.homedesign/_template_new_project/`）→ 實作前需確認已建好
- 歷史案（111–114年完工）的批量匯入：手動逐筆建，或提供 CSV import？（本 change 先做 UI 手動建）
