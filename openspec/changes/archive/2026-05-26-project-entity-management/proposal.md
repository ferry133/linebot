## Why

系統目前以 Trello board name（字串）作為「專案」的唯一識別，導致 user ↔ 專案關聯無法反查、通知收件人解析脆弱、NAS 資料夾與 DB 之間沒有穩定連結。隨著客戶數增加（含回頭客歷史案），需要一個有穩定 ID 的 Project 實體作為全系統的 correlation 中心。

## What Changes

- 新增 `projects` 資料表，以 UUID 為穩定 ID，記錄 Trello board 綁定、NAS 路徑、案號、狀態
- 新增 `line_user_projects` 關聯表，取代 `line_users.projects` JSONB 欄位，支援正查（此 user 的專案）與反查（此專案的所有人員）
- Admin UI 新增「專案管理」頁面：建立/編輯/封存專案，assign user 至專案
- 建立專案時自動產生民國年案號（如 `115年第3案`），並在 NAS 上 copytree template 資料夾
- **BREAKING**：`line_users.projects` JSONB 欄位資料遷移至 `line_user_projects`，遷移後原欄位廢棄
- 通知收件人解析改為 `board_id → project_id → line_user_projects`，取代 board_name 字串比對

## Capabilities

### New Capabilities

- `project-registry`: 專案實體的 CRUD，含案號生成、狀態管理（active/completed/archived）、Trello board 綁定、NAS 路徑記錄
- `project-nas-provisioning`: 建立專案時自動在 NAS copytree template 資料夾，路徑寫回 projects 表；NFS mount 進 pod
- `project-user-assignment`: user ↔ project 多對多關聯（含 relation 欄位：customer/vendor），支援正查與反查

### Modified Capabilities

- `line-user-registry`: `projects` 欄位語意改變——原 JSONB 字串陣列廢棄，改由 `line_user_projects` 表提供
- `role-based-access-control`: `_get_allowed_boards()` 的資料來源從 JSONB 改為 JOIN `line_user_projects → projects`
- `user-management-ui`: 新增「專案管理」分頁；user 編輯介面中的專案選擇從 board name chips 改為 project 實體選擇

## Impact

- **DB**：新增 2 張表（`projects`、`line_user_projects`）；migration 腳本遷移現有 JSONB 資料
- **k8s**：linebot Deployment 需掛 NFS PersistentVolume（`10.9.1.12:/volume2/jia.homedesign`）
- **`agents/customer_service.py`**：`_get_allowed_boards()` 查詢邏輯改寫
- **`agents/admin_server.py`**：新增 `/api/projects` CRUD endpoints；HTML 新增專案管理 UI
- **`trello_line_notifier.py`**：收件人解析路徑改為 board_id → project_id → line_user_projects
- **無外部 API 新增**：NAS 操作用 os/shutil（pod 掛載後）
