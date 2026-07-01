## 1. 內容引擎 as_of 穿透（trello_line_notifier.py）

- [x] 1.1 `days_diff(d, ref=None)`：`ref` 預設 `date.today()`
- [x] 1.2 `run_checks(as_of=None)`：as_of 預設今日,往下傳 `check_item`/`_in_summary`/`_summary_overdue`
- [x] 1.3 `check_item`、`_in_summary`、`_summary_overdue` 以傳入 `as_of` 取代 today（內部 days_diff 帶 ref）
- [x] 1.4 `build_daily_messages_for_user(user_id, role, as_of=None)`：透傳 as_of；標頭顯示選定日 + 「依目前進度推算」（as_of≠今日時）；someday `show_buttons=False`

## 2. gateway 擷取 datetimepicker params

- [x] 2.1 webhook postback 事件：擷取 `event["postback"]["params"]`（含 `date`）並隨 payload 轉發（既有 `data` 解析不動）

## 3. customer_service 路由

- [x] 3.1 `_process_postback`：`o=someday` → 讀 `params.date` → 解析為 `date` → `_handle_daily(uid, reply_token, as_of=選定日)`
- [x] 3.2 `_handle_daily(user_id, reply_token, as_of=None)`：透傳 as_of；缺值/格式錯 → 回退今日或提示；空內容回覆仍含入口按鈕

## 4. datetimepicker 入口按鈕

- [x] 4.1 每日輸出追加「📅 查其他日期」datetimepicker 按鈕（`mode=date`、`data=o=someday`、`min/max` 限 ±365 天）
- [x] 4.2 空內容（今日/該日無提醒）回覆仍附此按鈕

## 5. 驗證

- [x] 5.1 選未來日（如 +30 天）→ 屆時到期/逾期工項以該日基準呈現；選過去日 → 以當時日曆呈現
- [x] 5.2 標頭顯示選定日 + 「依目前進度推算」；someday 無 ✅完成 按鈕
- [x] 5.3 各角色（含 customer）RBAC 範圍不變；vendor 只自己、customer 只其看板
- [x] 5.4 空內容仍含「查其他日期」按鈕；缺 date/格式錯不崩潰
- [x] 5.5 今日提醒（as_of=None）行為與現況一致；py_compile 通過

## 6. 部署

- [x] 6.1 bump image（gateway + customer-service + notifier 同 image）
- [x] 6.2 部署後實機：datetimepicker 選日 → 回覆該日內容（含唯讀、標頭、入口按鈕）
