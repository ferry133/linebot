## Context

專案標籤含屋主姓名（PII），來自兩處：`projects.name`（`{owner}-{site}-{type}`）與 Trello 看板名（同格式）。兩者都漏進 LINE 顯示（每日通知/摘要/確認卡/查詢/拉取）。`projects` 已有結構欄位 `owner_name / site_name / project_type / case_number`；`sites` 表 key=(owner_name, site_name)，一建案多 project_type 共用一列。掃描現有 7 個 active 專案：全部具 site_name+project_type（缺漏 0）、卡片/工項名 0 筆含屋主名 → fix 範圍僅「專案標籤」。

## Goals / Non-Goals

**Goals:** LINE 全面以 `{site_name}-{project_type}` 顯示專案；保證該標籤唯一（admin 端強制 + 拒絕說明）；不洩漏屋主名。
**Non-Goals:** 不改 Trello 看板名、不改 sites 表、不改卡片/工項名、不改 RBAC 過濾與推播額度邏輯。

## Decisions

**1. 唯一性放在 `(site_name, project_type)`，非 site_name 單欄**
`sites` 表故意讓一個 site_name 被多個 project_type 共用（GPS/NAS 每建案填一次）。若逼 site_name 單欄唯一會破壞此模型。改以 `(site_name, project_type)` 部分唯一索引（僅 active），天生對應對外標籤、不動 sites。殘餘碰撞（同建案+同工種+不同屋主）由 admin 改 site_name 解決，系統擋下並說明。

**2. 對外標籤集中於單一 helper**
`public_label(project|board_id)` = `{site_name}-{project_type}`，缺欄位→`case_number`。所有顯示路徑改呼叫它，杜絕各處各自組字串。board_id→label 對照在 notifier（`_all_project_names` 改回 label）與 customer_service（`_get_user_auth` 的 project_map）建立。

**3. 移除看板名 fallback**
trello-agent 與 notifier 原本查不到對照時退回 Trello 看板原名（含屋主）。改為退回 `case_number`，永不顯示看板原名。

**4. 唯一性檢查只在 active**
completed/archived 不納入，避免歷史案卡住新案；符合既有 case_number「不填補空缺」風格。

## Risks / Trade-offs

- [主管在 LINE 失去屋主名便利] → 使用者已確認接受（B：一律對外）；改於 Trello/admin UI 查。
- [未填 site_name/type 的 legacy 案] → 後備 case_number，仍不洩漏；現有 active 0 筆缺漏。
- [部署需 bump 多 workload image] → 沿用 `scripts/bump-linebot-image.sh`（notifier+agents 同一 image）。
- [既有資料若已存在 (site,type) 重複的 active 案] → 建索引前需先確認無衝突；migration 採 partial unique，衝突會建索引失敗 → 上線前先查並請 admin 改名。
