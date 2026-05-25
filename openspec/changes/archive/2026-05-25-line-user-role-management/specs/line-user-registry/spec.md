## ADDED Requirements

### Requirement: Auto-register LINE user on first contact
當 LINE 用戶首次傳訊息時，系統 SHALL 自動呼叫 LINE Profile API 取得用戶資料，並在 `line_users` table 建立記錄，初始 role 為 `visitor`。若用戶已存在，SHALL 更新 `display_name` 與 `picture_url`，但不得覆蓋已設定的 `role` 與 `projects`。

#### Scenario: New user sends first message
- **WHEN** gateway 收到一個從未出現過的 LINE user_id 的訊息
- **THEN** 系統呼叫 LINE Profile API 取得 displayName 與 pictureUrl
- **THEN** 在 `line_users` 建立記錄：role=visitor, projects=[]
- **THEN** 訊息正常轉發至 customer-service-agent，不延遲

#### Scenario: Existing user sends message
- **WHEN** gateway 收到已存在 `line_users` 記錄的用戶訊息
- **THEN** 系統 upsert 更新 display_name 與 picture_url
- **THEN** role 與 projects 維持不變

#### Scenario: LINE Profile API fails
- **WHEN** LINE Profile API 回傳錯誤或逾時
- **THEN** 系統以 line_id 僅建立最小記錄（display_name=null），不阻斷訊息處理
- **THEN** 記錄 warning log，不拋出例外

### Requirement: line_users DB schema
系統 SHALL 維護 `line_users` table，欄位包含：line_id（PK）、display_name、picture_url、role、projects（JSONB）、created_at、updated_at。

#### Scenario: Schema integrity
- **WHEN** 新建 `line_users` 記錄未指定 role
- **THEN** role 預設為 `visitor`，projects 預設為空陣列 `[]`
