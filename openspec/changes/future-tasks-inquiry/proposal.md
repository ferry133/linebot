## Why

現有 someday 只能挑**單一日期**看那天觸發的工項,無法一眼看「未來一段期間會發生什麼」。使用者要的是**區間總覽**:未來(或過去)一段期間內,哪些工項會開始/到期。

## What Changes

- **新增「未來工項」區間清單**:Rich Menu 一格「未來工項」→ 列出選定**方向×視窗**內、未完成、且**開始日或結束日**落在該區間的工項,**依日期排序**、標「開始/到期」。
  - **方向×視窗**：以 quick-reply 選——未來(2週/1月/2月/3月)或過去(2週/1月/2月/3月);點按 Rich Menu 預設「未來1月」。
  - **RBAC 不變**:supervisor 全部、vendor 自己被 tag、customer 其看板。**唯讀**(無 ✅完成)。**投影**:以目前進度重算,附「依目前進度推算」。
- **保留單日查詢(someday)為子選項**:區間清單訊息附「📅 指定日期」quick-reply → 沿用既有 datetimepicker(過去/未來單日投影)。
- **Rich Menu 調整**:中間格「查其他日期」→「未來工項」(`postback o=future`);單日 datetimepicker 由 Rich Menu 一級入口降為「未來工項」內的 quick-reply。

## Capabilities

### New Capabilities
- `future-tasks-inquiry`: 未來/過去區間工項清單(方向×視窗、依日期排序、RBAC、唯讀、投影),含單日查詢子入口。

### Modified Capabilities
- `daily-notice-on-demand`: Rich Menu 中間格由「指定日期(someday)」改為「未來工項」入口。
- `someday-reminder`: 單日 datetimepicker 入口由 Rich Menu 一級改為「未來工項」內的「指定日期」quick-reply(引擎與投影/唯讀不變)。

## Impact

- `trello_line_notifier.py`:新增 `build_future_messages_for_user(user_id, role, direction, window)`——`_scan_boards()` 掃描 → 收未完成、有 tag、start 或 end 落在區間的工項 → 依日期排序、標開始/到期 → RBAC 過濾 → Flex(依日期分組)+ quick-reply(方向×視窗 + 指定日期)。唯讀、附推算註記。
- `agents/customer_service.py`:`_process_postback` 新增 `o=future`(讀 `dir`/`n` 參數)→ `_handle_future`;quick-reply 的「指定日期」仍走既有 `o=someday`。
- `gateway/setup_richmenu.py`:中間格 label「未來工項」、action `postback o=future`;重繪底圖 + 重新部署 Rich Menu。
- 不影響今日提醒、每日 push、someday 單日引擎、RBAC 範圍。
