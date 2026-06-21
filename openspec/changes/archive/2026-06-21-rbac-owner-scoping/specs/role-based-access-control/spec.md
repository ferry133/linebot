## MODIFIED Requirements

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

## ADDED Requirements

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
