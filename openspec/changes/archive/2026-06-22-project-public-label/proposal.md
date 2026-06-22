## Why

專案標籤目前是 `{owner_name}-{site_name}-{project_type}`（同時來自 `projects.name` 與 Trello 看板名），裡頭含**屋主姓名（PII）**。這個標籤出現在所有 LINE 顯示（每日通知標頭、每日摘要、待主管確認卡、查詢回覆、Rich Menu 拉取），導致**廠商等非相關人員看得到客人姓名**。需要一個不含 PII 的對外標籤，並在 LINE 全面改用它。

## What Changes

- 定義**對外標籤** `public_label = {site_name}-{project_type}`（永不含 owner_name）。
- **所有 LINE 顯示一律改用 public_label**（不分角色，含主管）；MUST NOT 再把 `projects.name` 或 Trello 看板原名呈現給任何 LINE 使用者。移除「fallback 到 Trello 看板名」這條漏點。
- 為確保標籤無歧義：active 專案的 `(site_name, project_type)` SHALL 唯一；admin 建立/更新造成重複時**擋下並回明確原因**（請把 `site_name` 改成可區分，如加棟別/戶別）。
- Trello 看板名、`sites` 表、卡片/工項名稱**不動**（卡片/工項已驗證不含屋主名）。主管要查屋主名改於 Trello / admin UI。

## Capabilities

### New Capabilities
- `project-public-label`: 對外（LINE）一律以不含 PII 的 `{site_name}-{project_type}` 呈現專案；定義 fallback 與「所有顯示路徑皆用此標籤、不得回 projects.name / 看板原名」的規範。

### Modified Capabilities
- `project-registry`: 新增「active 專案 `(site_name, project_type)` 唯一」約束，建立/更新重複時拒絕並回原因。

## Impact

- DB：新增部分唯一索引 `UNIQUE(site_name, project_type) WHERE status='active'`（新 migration）。
- `agents/admin_server.py`：`POST/PUT /api/projects` 偵測 `(site_name, project_type)` 重複 → 409 + 原因。
- 新 helper `public_label(project|board_id)`（site-type；缺欄位→case_number 兜底）。
- 顯示替換：`trello_line_notifier.py`（`run_checks` 顯示用 board 標籤、`build_flex` 標頭、確認卡、`_all_project_names`）、`agents/customer_service.py`（`_get_user_auth` 的 project_map）、`agents/trello_agent.py`（`project_name` 標示 + 移除看板名 fallback）。
- 不影響推播額度、RBAC 過濾邏輯（純顯示字串改變）。
