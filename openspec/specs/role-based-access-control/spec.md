## ADDED Requirements

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
系統 SHALL 在處理每則訊息時，從 `line_users` DB table 查詢該用戶的 role 與 projects，不得使用快取超過單次請求範圍。

#### Scenario: Permission check
- **WHEN** customer-service-agent 準備呼叫 query_trello 工具
- **THEN** 先查詢 `line_users` 取得 allowed_boards
- **THEN** 將 allowed_boards 帶入 MQTT request 傳給 trello-agent

#### Scenario: User not in DB
- **WHEN** line_id 不存在於 `line_users`（極少數情況，建檔失敗）
- **THEN** 視為 visitor，回傳無權限訊息
