## Purpose
角色與權限模型：定義 admin/employee/vendor/customer/visitor 五種角色及其資料查詢權限邊界。
## Requirements
### Requirement: Role definitions
系統 SHALL 支援五種角色，各角色對 Trello 工項的存取權限如下：

| Role | 存取範圍 |
|------|---------|
| admin | 所有專案（無限制） |
| employee | 所有專案（無限制） |
| vendor | **僅自己被指派的工項**（工項標記 `[@(alias)]` 的 names 含其 alias），即使同看板亦不得見他人工項 |
| customer | 僅 projects 欄位指定的看板（該看板全部工項，屋主可見案場全貌） |
| visitor | 無存取權限 |

#### Scenario: Admin queries Trello
- **WHEN** role=admin 的用戶查詢工程進度
- **THEN** trello-agent 回傳所有看板的工項，不過濾

#### Scenario: Vendor queries Trello（owner 層級）
- **WHEN** role=vendor 且 alias=larryoffice 的用戶查詢工程進度
- **THEN** trello-agent 只回傳 names 含 "larryoffice" 的工項；同看板其他負責人的工項 MUST NOT 出現

#### Scenario: Customer queries Trello
- **WHEN** role=customer 且 projects=["王小明_信義路"] 的用戶查詢工程進度
- **THEN** trello-agent 回傳 "王小明_信義路" 看板的全部工項（不以 owner 過濾）

#### Scenario: Visitor queries Trello
- **WHEN** role=visitor 的用戶詢問工程進度
- **THEN** 系統回覆「您目前沒有工程查詢權限，如有需要請聯繫我們的服務人員。」
- **THEN** 不向 trello-agent 發送 MQTT request

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

### Requirement: 廠商工項可見性以擁有者為界（跨對話與通知）
廠商的工項可見性 SHALL 一致地收斂到擁有者層級，套用於兩條路徑：(1) 對話查詢 `query_trello`、(2) 每日通知與 Rich Menu on-demand 拉取。系統 MUST 僅向廠商呈現其被 `[@(alias)]` 指派的工項，MUST NOT 因看板共享而洩漏他人工項或主管專屬內容（每日摘要、待主管確認卡）。系統 MUST NOT 以任何跨帳號鏡像（如舊有「通知 larry 即同步通知 larryoffice」）將某帳號內容複製給另一帳號；跨帳號可見性僅能由各帳號自身角色決定。

#### Scenario: 對話查詢的 owner 過濾
- **WHEN** role=vendor 透過 `query_trello`（含 all/overdue/upcoming/specific）查詢
- **THEN** customer-service 帶入該廠商的 `owner_alias`，trello-agent 於板層授權後再以 owner 過濾，僅回其被指派工項

#### Scenario: 通知/拉取不洩漏主管內容
- **WHEN** role=vendor 收到每日 push 或點 Rich Menu「今日提醒」
- **THEN** 內容僅含其被指派工項，MUST NOT 含每日摘要或待主管確認卡

#### Scenario: 無跨帳號鏡像
- **WHEN** 任一主管帳號（如 larry）產生通知內容
- **THEN** 系統 MUST NOT 將其內容鏡像複製給其他帳號（如 larryoffice）；larryoffice 僅依自身 role=vendor 取得自己的工項

