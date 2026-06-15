## Purpose
工程通知的聯絡人來源整合：`trello_line_notifier.py` 從 `line_users` DB table 解析收件人，並把 alias 解析失敗等訊號呈現給營運者。

## Requirements

### Requirement: contacts data source
`trello_line_notifier.py` 的 `load_contacts()` SHALL 從 `line_users` DB table 讀取，回傳 `{name_lower: line_id}` 格式（與現有呼叫方簽名相容）。contacts.json 不再作為主要資料來源。

#### Scenario: Load contacts from DB
- **WHEN** trello-notifier CronJob 執行通知邏輯
- **THEN** `load_contacts()` 查詢 `line_users` WHERE role IN ('admin','employee','vendor','customer')
- **THEN** 回傳 `{display_name.lower(): line_id}` dict

#### Scenario: DB unavailable
- **WHEN** DB 連線失敗
- **THEN** `load_contacts()` 回傳空 dict 並記錄 error log
- **THEN** CronJob 繼續執行但不發送通知（不 crash）

### Requirement: contacts.json migration
系統 SHALL 提供一次性 migration script，將 contacts.json 的現有資料 upsert 進 `line_users` table。

#### Scenario: Migrate employee contacts
- **WHEN** 執行 migration script
- **THEN** contacts.json 中 projects="*" 的聯絡人以 role=employee 寫入 DB
- **THEN** contacts.json 中 projects=[...] 的聯絡人以 role=customer 寫入 DB
- **THEN** 已存在的 DB 記錄不被覆蓋（ON CONFLICT DO NOTHING）

### Requirement: internal-notice recipients

工程通知中屬於「內部提醒」性質的項目——#3（到期前 1–7 天）、#4（今日到期）、#5（今日逾期）、#6（已逾期 X 天）、#7（Checklist 停滯 > 3 天）、#9（每日摘要）——其內部收件人 SHALL 解析為 `line_users` 中 `role IN ('admin','employee')` 的全體 LINE 帳號（即「所有管理者/員工」），而非固定的 `sa` / `larry` 兩個 alias。sponsor（`@(...)` 標記對象）的解析與 #1 / #2 / #8 僅發給 sponsor 的行為 MUST 維持不變。

#### Scenario: 內部提醒發給所有管理者/員工
- **WHEN** trello-notifier 觸發 #3–#7 或 #9 的內部通知
- **THEN** 查詢 `line_users` WHERE `role IN ('admin','employee')`，取其 `line_id` 全集作為內部收件人
- **THEN** #3–#6 的收件人為 `sponsor ∪ 所有管理者/員工`；#7、#9 的收件人為 `所有管理者/員工`

#### Scenario: 無管理者/員工時靜默
- **WHEN** `line_users` 中查無 `role IN ('admin','employee')` 的帳號，或 DB 連線失敗
- **THEN** 內部收件人為空集合，內部通知該次不送內部份並記錄 log
- **THEN** sponsor 份（#1/#2/#8 及 #3–#6 的 sponsor 部分）不受影響

### Requirement: unresolved alias visibility

當 Trello 標記用到的名字在 `line_users.alias_name` 查無對應時，`trello_line_notifier.py` SHALL 在該次 run 收集這些未對應的名字（去重），並在 **morning 每日摘要（#9）** 尾端附加一段警告清單呈現給收件者（所有管理者/員工）。系統 MUST NOT 讓此訊號僅停留在 log。noon／evening 的行為 MUST 維持不變。

#### Scenario: 早報附加未對應清單
- **WHEN** morning run 期間，有一或多個 Trello 標記名字在 `line_users.alias_name` 查無對應
- **THEN** 每日摘要訊息尾端附加一段標題含「⚠️」的區塊，列出所有未對應的名字（去重）
- **THEN** 摘要仍正常發送給原本的收件者（所有管理者/員工）

#### Scenario: 無未對應時不顯示
- **WHEN** morning run 期間所有 Trello 標記名字都成功對應到 line_id
- **THEN** 每日摘要不含任何未對應警告段落（與本變更前的輸出一致）

#### Scenario: 非 morning 時段不改變行為
- **WHEN** noon 或 evening run 遇到未對應的 alias
- **THEN** 不產生面向使用者的未對應清單（維持既有行為，僅原有 log 警告）
