## Purpose
角色與權限模型：定義 admin/employee/vendor/customer/visitor 五種角色及其資料查詢權限邊界。
## Requirements
### Requirement: Role definitions
系統 SHALL 支援五種角色，各角色對 Trello 專案的存取權限如下：

| Role | 存取範圍 |
|------|---------|
| admin | 所有專案（無限制） |
| employee | 所有專案（無限制） |
| vendor | 僅 projects 欄位指定的看板 |
| customer | 僅 projects 欄位指定的看板 |
| visitor | 無存取權限 |

#### Scenario: Admin queries Trello
- **WHEN** role=admin 的用戶查詢工程進度
- **THEN** trello-agent 回傳所有看板的工項，不過濾

#### Scenario: Customer queries Trello
- **WHEN** role=customer 且 projects=["王小明_信義路"] 的用戶查詢工程進度
- **THEN** trello-agent 只回傳 "王小明_信義路" 看板的工項

#### Scenario: Visitor queries Trello
- **WHEN** role=visitor 的用戶詢問工程進度
- **THEN** 系統回覆「您目前沒有工程查詢權限，如有需要請聯繫我們的服務人員。」
- **THEN** 不向 trello-agent 發送 MQTT request

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

