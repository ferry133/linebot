## 1. 資料庫 Migration

- [x] 1.1 建立 `migrations/004_alias_name.sql`：`line_users` 加 `alias_name TEXT UNIQUE` 欄位；以 display_name lowercase 比對填入現有 larry/sa/yan（找不到者 log WARNING）
- [x] 1.2 建立 `migrations/005_projects.sql`：`projects` 表（UUID PK、case_number、name、trello_board_id nullable、nas_path nullable、status、started_at、completed_at、created_at、updated_at）
- [x] 1.3 建立 `migrations/006_line_user_projects.sql`：`line_user_projects` 表（line_id FK、project_id FK、relation、created_at、PRIMARY KEY (line_id, project_id)）
- [x] 1.4 建立 `migrations/007_migrate_jsonb_projects.sql`：將 `line_users.projects` JSONB 資料遷移至新表（board_name → trello_boards → board_id → projects → line_user_projects，孤兒 board_name 記 WARNING）
- [x] 1.5 在 `shared/db.py` 的 migration runner 中加入新的 migration 檔案

## 2. k8s NFS 掛載

- [x] 2.1 在 per-user k8s repo 的 linebot HelmRelease `values.persistence` 新增 `type: nfs` 區段（server: `${NAS_SERVER}`, path: `/volume2/jia.homedesign`, globalMounts path: `/mnt/nas/jia.homedesign`），參考 jg-base `claude-code` helmrelease 的 workspace persistence 寫法，不建 PV/PVC manifest

## 3. Project Registry API

- [x] 3.1 在 `agents/admin_server.py` 新增案號生成函式 `_generate_case_number(year)`：查 `projects` 取當年 MAX 流水號 + 1，回傳 `{民國年}年第{N}案`
- [x] 3.2 實作 `GET /api/projects`（支援 filter: status, year）
- [x] 3.3 實作 `POST /api/projects`（觸發案號生成、NAS provisioning、insert DB）
- [x] 3.4 實作 `PUT /api/projects/<project_id>`（更新 name、trello_board_id、status；status→archived 時設 completed_at）
- [x] 3.5 實作 `GET /api/projects/<project_id>`（單筆查詢）

## 4. NAS Provisioning

- [x] 4.1 在 `agents/admin_server.py` 實作 `_provision_nas_folder(folder_name) → nas_path | None`：檢查 template 路徑存在、copytree、回傳完整路徑；template missing 或衝突時記 log 並回傳 None
- [x] 4.2 在 `POST /api/projects` 中呼叫 `_provision_nas_folder`，成功後更新 `projects.nas_path`；folder 已存在回傳 409 並 rollback project insert
- [x] 4.3 新增環境變數 `NAS_MOUNT_PATH`（預設 `/mnt/nas/jia.homedesign`）供 provisioning 函式使用

## 5. Project-User Assignment API

- [x] 5.1 實作 `PUT /api/projects/<project_id>/users`（全量替換該專案的 line_user_projects 記錄）
- [x] 5.2 實作 `GET /api/projects/<project_id>/users`（回傳人員清單含 display_name、relation）
- [x] 5.3 實作 `GET /api/users/<line_id>/projects`（回傳該 user 的所有專案含 relation）

## 6. RBAC 查詢改寫

- [x] 6.1 在 `agents/customer_service.py` 改寫 `_get_allowed_boards(user_id)`：改 JOIN `line_user_projects → projects` 查 trello_board_id，取代原本讀 `line_users.projects` JSONB
- [x] 6.2 驗證 admin/employee role 仍回傳 None（無限制），visitor 仍回傳 []

## 7. 通知收件人解析改寫

- [x] 7.1 在 `trello_line_notifier.py` 改寫 `_resolve_tag_recipients(names) → list[str]`：改查 `SELECT line_id FROM line_users WHERE alias_name = ANY(%s)`（小寫比對），取代 contacts dict lookup；alias 找不到時 log WARNING
- [x] 7.2 在 `trello_line_notifier.py` 新增 `_resolve_recipients_by_board_id(board_id) → list[str]`：查 projects → line_user_projects → line_id；board_id 無對應時 log WARNING 回傳 []
- [x] 7.3 將現有通知推播邏輯改用兩個函式：員工/廠商標記走 alias_name 查詢，客戶推播走 board_id 查詢

## 8. Admin UI — alias_name 管理

- [x] 8.1 在 `PUT /api/users/<line_id>` endpoint 支援更新 `alias_name` 欄位（衝突時回傳 409）
- [x] 8.2 user 編輯 dialog 新增 `alias_name` text input 欄位，附提示文字「用於 Trello 標記，設定後請避免變更」
- [x] 8.3 user 列表每筆若有 alias_name，顯示灰色小 badge 於 display_name 旁

## 9. Admin UI — Projects 分頁

- [x] 9.1 在 `admin_server.py` 的 inline HTML 新增「Projects」tab
- [x] 9.2 實作專案列表 view（案號、名稱、Trello 看板名稱、NAS 路徑、狀態、人員數）
- [x] 9.3 實作「新增專案」表單（name、folder_name、trello_board_id 下拉、備註）
- [x] 9.4 實作「編輯專案」dialog（name、trello_board_id、status；nas_path 唯讀）
- [x] 9.5 實作專案人員 assign UI：在 project 卡片展開後顯示人員列表，支援新增/移除 user（relation: customer/vendor）

## 10. Admin UI — User 編輯改寫

- [x] 10.1 user 編輯 dialog 的「專案」勾選清單改為從 `GET /api/projects?status=active` 拉取，顯示 `{案號} {名稱}`
- [x] 10.2 儲存時改呼叫 `PUT /api/projects/<id>/users` 更新 line_user_projects（不再寫 line_users.projects JSONB）

## 11. 測試與驗證

- [x] 11.1 NAS template 改用現有 SOP 資料夾：`C.公司SOP表單 and Check list/01.新開案資料夾：電腦檔案資料夾編號順序01.02.03`；`NAS_TEMPLATE_PATH` env var 預設值已更新
- [x] 11.2 apply migration 004–007：在 `admin_server.py` 啟動時自動呼叫 `run_migrations()`；確認 004 的 alias_name 填入正確（larry/sa/yan），007 的遷移 WARNING log 列出孤兒 board_name
- [ ] 11.3 透過 Admin UI 設定 larry/sa/yan 的 alias_name，確認唯一性驗證正常
- [ ] 11.4 透過 Admin UI 建立一個測試專案，確認案號生成正確、NAS 資料夾建立、DB record 寫入
- [ ] 11.5 透過 Admin UI assign customer user 至測試專案；以該 user 身分傳訊測試 RBAC 查詢走新路徑
- [ ] 11.6 build & push 新 image，rollout restart；確認 NFS mount 成功
- [ ] 11.7 驗證通知腳本（dry-run 或測試 board）能正確以 alias_name 解析收件人
