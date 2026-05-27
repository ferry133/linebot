## MODIFIED Requirements

### Requirement: Permission lookup from DB
系統 SHALL 在處理每則訊息時，從 `line_user_projects` JOIN `projects` 查詢該用戶可存取的 trello_board_id 清單，不得使用 `line_users.projects` JSONB 欄位。

#### Scenario: Permission check via new table
- **WHEN** customer-service-agent 準備呼叫 query_trello 工具
- **THEN** 查詢 `SELECT p.trello_board_id FROM line_user_projects lup JOIN projects p ON lup.project_id = p.project_id WHERE lup.line_id = %s AND p.status = 'active'`
- **THEN** 將 allowed_board_ids 帶入 MQTT request 傳給 trello-agent

#### Scenario: User not in DB
- **WHEN** line_id 不存在於 `line_users`（極少數情況，建檔失敗）
- **THEN** 視為 visitor，回傳無權限訊息

#### Scenario: Customer with no assigned projects
- **WHEN** role=customer 但 line_user_projects 無對應記錄
- **THEN** allowed_board_ids = []，視為無存取權限
