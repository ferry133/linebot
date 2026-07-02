## Why

「今日提醒」只能看**當天**的工程提醒。使用者常需要看**其他日期**的狀態——例如「下週三(未來)哪些工項該開始/到期?」或「上週五(過去)那天的提醒是什麼?」。目前無此能力。

## What Changes

- 新增「指定日期提醒(someday)」：使用者在今日提醒下方點 **LINE 日期選擇器按鈕**(datetimepicker)選一個**過去或未來**日期 → 以該日為基準計算並回覆對應的提醒內容(免費 Reply)。
- **各角色皆可用**(admin/employee/vendor/customer);RBAC 可見範圍**不變**——只是把「今天」換成選定日期。內容引擎與今日提醒**共用**(#1–#9 觸發、進行中窗口皆改以選定日判定)。
- **投影語意(非歷史快照)**：Trello 無歷史狀態,故 someday 以**目前**各工項完成/清單狀態,重新用**選定日的日曆**評估日期條件(開始倒數/到期/逾期/進行中窗口)。過去日=「以當時日曆＋目前進度」、未來日=「若維持現況的推算」。標頭明示「依目前進度推算」。
- **唯讀**：someday 內容**不含 ✅完成 按鈕**(對非當日的投影按完成易混淆);要操作請用今日提醒。

## Capabilities

### New Capabilities
- `someday-reminder`: 以 datetimepicker 指定過去/未來日期,回覆該日(投影)提醒;共用內容引擎、沿用 RBAC、唯讀、各角色可用。

### Modified Capabilities
- `daily-notice-on-demand`: 今日提醒(及 someday 回覆)輸出**追加**「📅 查其他日期」datetimepicker 按鈕作為 someday 入口;空內容時仍提供該按鈕。

## Impact

- `gateway/line_gateway.py`：`_parse_postback` 之外,webhook 需擷取 `postback.params`(datetimepicker 的 `date`)並隨 payload 轉發。
- `agents/customer_service.py`：`_process_postback` 新增 `o=someday`(讀 params.date)→ `_handle_daily(..., as_of=選定日)`;`_handle_daily` 加 `as_of`。
- `trello_line_notifier.py`：`run_checks(as_of=None)`、`build_daily_messages_for_user(user_id, role, as_of=None)`、`days_diff`/`_in_summary`/`_summary_overdue`/`check_item` 以 `as_of` 取代 today;標頭顯示選定日 + 「依目前進度推算」;someday 唯讀(show_buttons=False);今日提醒輸出追加 datetimepicker 按鈕。
- 不影響每日 push(仍以真實今日)、確認流程、RBAC 範圍。
