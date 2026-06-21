# consolidated-daily-notification Specification

## Purpose
TBD - created by archiving change supervisor-confirm-card-context. Update Purpose after archive.
## Requirements
### Requirement: 單一每日批次評估全部觸發條件

系統 SHALL 以**單一每日批次**（每日執行一次）取代原本 morning / noon / evening 三批次，於該次執行評估全部既有觸發條件（#1 開始倒數、#2 今日開始、#3 結束倒數、#4 今日到期、#5/#6 逾期、#7 停滯、#8 全完成、#9 每日摘要）。各條件原有判定語意與完成狀態抑制規則 MUST 維持不變（僅執行時機合併為一次）。系統 MUST NOT 再以 noon 或 evening 名義另行推播。

#### Scenario: 每日一次評估所有條件
- **WHEN** 每日批次執行
- **THEN** 系統評估 #1–#9 全部觸發條件，產生該日所有應發項目

#### Scenario: 不再有 noon/evening 批次
- **WHEN** 一天之內
- **THEN** 系統至多執行一次每日批次，MUST NOT 於中午或傍晚另行推播工項提醒

### Requirement: 主動推播僅送廠商

每日批次的**主動 push** SHALL 僅送給 `role = vendor` 的收件人。`role ∈ {admin, employee}`（主管）與 `role = customer`（客戶）**MUST NOT** 收到主動 push；其每日內容改由 on-demand 拉取取得（見 `daily-notice-on-demand`）。每位 vendor 收件人當日所有應發內容 SHALL 合併為**單一 Flex carousel** 以一則 push 送出；超過 carousel bubble 上限時截斷至上限，MUST NOT 為同一人同一批次拆成第二則。

#### Scenario: 廠商收到主動 push
- **WHEN** 某 role=vendor 收件人當日有應發工項
- **THEN** 系統將其當日內容合併為單一 carousel，以一則 push 送出

#### Scenario: 主管與客戶不被主動 push
- **WHEN** 每日批次執行
- **THEN** 系統 MUST NOT 對 role∈{admin,employee} 或 role=customer 的收件人送出主動 push

### Requirement: 無內容不主動推播

當某 vendor 收件人該日**無任何應發工項**時，系統 MUST NOT 對其送出主動 push，以節省推播額度。此規則取代既有「morning 摘要無進行中工項仍送出佔位訊息」的行為。（on-demand 拉取不受此限——拉取一律回覆，無內容時回覆「今日無提醒」。）

#### Scenario: 廠商當日無內容不送
- **WHEN** 某 vendor 收件人該日無任何應發工項
- **THEN** 系統不對其送出主動 push（不計入推播額度）

