## MODIFIED Requirements

### Requirement: line_users DB schema
系統 SHALL 維護 `line_users` table，欄位包含：line_id（PK）、display_name、picture_url、role、alias_name（TEXT, nullable, unique）、projects（JSONB, **廢棄**）、created_at、updated_at。`projects` 欄位 SHALL 不再被讀取或寫入；user ↔ project 關聯改由 `line_user_projects` 表管理。

#### Scenario: Schema integrity
- **WHEN** 新建 `line_users` 記錄未指定 role
- **THEN** role 預設為 `visitor`，projects 欄位可為任意值（不讀取）

## ADDED Requirements

### Requirement: alias_name 欄位
系統 SHALL 在 `line_users` 維護 `alias_name` 欄位，作為該用戶在系統內的穩定簡稱（小寫英數字，全表唯一，可為 null 表示未設定）。此 alias 獨立於 LINE display_name，由 Admin 手動設定，不因 display_name 變更而改變。`alias_name` 可用於任何需要簡短、穩定識別符的場景（如 Trello 標記、未來 webhook 路由等）。

#### Scenario: alias_name uniqueness
- **WHEN** Admin 設定某 user 的 alias_name = "wang"
- **THEN** 若 "wang" 已被其他 user 使用，系統回傳 409 錯誤
- **THEN** 若 "wang" 未被使用，成功更新

#### Scenario: Null alias
- **WHEN** user 未設定 alias_name
- **THEN** alias_name = null，不影響其他功能

### Requirement: Trello 通知收件人用 alias_name 解析
`trello_line_notifier` SHALL 將 Trello 標記中的 `(name)` 欄位與 `line_users.alias_name`（小寫比對）對應，取得 LINE user_id 以推播通知。不再依賴 contacts dict 的 key 名稱。

#### Scenario: Resolve alias from Trello tag
- **WHEN** Trello 標記為 `[@(larry)@(sa),-20260427]`
- **THEN** 查 `SELECT line_id FROM line_users WHERE alias_name IN ('larry', 'sa')`
- **THEN** 對查到的 line_id 推播通知

#### Scenario: Unknown alias in tag
- **WHEN** Trello 標記中的 name 無對應 alias_name
- **THEN** 記錄 WARNING log（`alias not found: xxx`），跳過該收件人，不拋出例外

### Requirement: alias_name 遷移
系統 SHALL 在 migration script 中，將現有 contacts dict（larry/sa/yan 等）的 key 自動填入對應 user 的 alias_name（以 display_name lowercase 比對，找不到者略過並 log WARNING）。

#### Scenario: Migration from contacts
- **WHEN** 套用 migration script
- **THEN** display_name = "Larry" → alias_name = "larry"
- **THEN** display_name = "SA" → alias_name = "sa"
- **THEN** display_name = "yan" → alias_name = "yan"
