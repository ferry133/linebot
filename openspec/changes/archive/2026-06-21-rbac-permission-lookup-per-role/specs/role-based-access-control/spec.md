## MODIFIED Requirements

### Requirement: Permission lookup from DB
系統 SHALL 在處理每則訊息時，從 `line_user_projects` JOIN `projects` 查詢權限，**不得**使用 `line_users.projects` JSONB 欄位。傳給 trello-agent 的 `allowed_board_ids`（板層授權；`None`=不限板、`[]`=封鎖、`[str]`=限定）SHALL 依角色決定：

| Role | allowed_board_ids |
|------|-------------------|
| admin / employee | `None`（不限板） |
| vendor | `None`（**不以板限制**；可見性僅由工項標記 `[@(alias)]` 經 `owner_alias` 過濾決定） |
| customer | `line_user_projects` 對應的 active 看板清單（無對應 → `[]`，視為無權限） |
| visitor | `[]`（無權限） |

vendor 雖回 `None`，呼叫端仍 MUST 帶入其 `owner_alias`，使 trello-agent 僅回其被 tag 的工項；故 vendor 的板層指派不影響其可見性。

#### Scenario: Customer board lookup
- **WHEN** role=customer 準備呼叫 query_trello 工具
- **THEN** 查詢 `SELECT p.trello_board_id FROM line_user_projects lup JOIN projects p ON lup.project_id = p.project_id WHERE lup.line_id = %s AND p.status = 'active'`
- **THEN** 將該看板清單作為 allowed_board_ids 帶入 MQTT request 傳給 trello-agent

#### Scenario: Vendor 不以板限制
- **WHEN** role=vendor 準備呼叫 query_trello 工具
- **THEN** allowed_board_ids = None（不以 line_user_projects 作板限制）
- **THEN** 帶入該 vendor 的 owner_alias，由 trello-agent 以工項標記過濾為唯一可見性依據

#### Scenario: User not in DB
- **WHEN** line_id 不存在於 `line_users`（極少數情況，建檔失敗）
- **THEN** 視為 visitor，回傳無權限訊息

#### Scenario: Customer with no assigned projects
- **WHEN** role=customer 但 line_user_projects 無對應記錄
- **THEN** allowed_board_ids = []，視為無存取權限
