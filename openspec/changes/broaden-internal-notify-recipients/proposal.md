## Why

目前工程通知的「內部收件人」固定為兩個 alias（`sa`、`larry`）。實務上希望由「所有管理者/員工」共同接收這些內部提醒，不再綁定特定兩人——新進員工或其他管理者也要能收到到期/逾期/停滯/每日摘要，且不必每次去 Trello 標記內加 alias。

## What Changes

- 把通知設計表中「SA/Larry」這組內部收件人，從固定的 `sa` + `larry` 兩個 alias 解析，改為解析 `line_users` 中 **role IN ('admin','employee')** 的全體 LINE 帳號。
- 影響項目：
  - **#3 / #4 / #5 / #6**（到期前 7 天、今日到期、今日逾期、已逾期 X 天）：收件人由 `sponsor + SA/Larry` → `sponsor + 所有管理者/員工`。
  - **#7**（Checklist 停滯 > 3 天）：收件人由 `SA / Larry` → `所有管理者/員工`。
  - **#9**（每日摘要，含未對應 alias 警告與「已完成未歸欄」警告）：收件人由 `SA / Larry` → `所有管理者/員工`。
- **不變**：#1 / #2 / #8 仍只發給 `sponsor`；sponsor（`@(...)` 標記）解析邏輯不變；larry→larryoffice 鏡像維持。
- 同步更新設計文件 `trello-line-design.md` 表格「通知對象」欄。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `contacts-integration`: 新增「內部通知收件人解析」需求，定義 #3–#7、#9 的內部收件人為 role IN ('admin','employee') 的全體帳號；並更新既有「unresolved alias visibility」需求中對收件人的描述（SA/Larry → 所有管理者/員工）。

## Impact

- 程式：`trello_line_notifier.py`
  - 新增 helper（解析 admin/employee 全體 line_id），取代 4 處 `_resolve_tag_recipients(["sa","larry"])`（check_item #3–#6、#7 停滯、#9 摘要）。
- 文件：`trello-line-design.md`（觸發條件表「通知對象」欄）。
- 行為：收件人擴大；無 DB 新欄位、無 migration。DB 無 admin/employee 時內部通知收件人為空（與目前 sa/larry 查無時一致，僅 log 警告）。
