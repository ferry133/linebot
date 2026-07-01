## Context

今日提醒(`daily-notice-on-demand`)以 `build_daily_messages_for_user(uid, role)` → `run_checks()` 產生內容,所有日期條件(#1–#9、進行中窗口)經 `days_diff(d)`＝`(d − date.today()).days` 相對**今天**判定。someday 要把「今天」換成使用者選定的任意日期,其餘完全共用。

## Goals / Non-Goals

**Goals:** datetimepicker 選過去/未來日 → 以該日為基準的提醒(投影)；各角色可用、RBAC 不變；唯讀。
**Non-Goals:** 不做 Trello 歷史狀態還原(無此資料)；不改每日 push(仍用真今日)；不改 RBAC 範圍、確認流程。

## Decisions

**1. `as_of` 顯式參數穿透內容引擎**
`days_diff(d, ref=None)` 的 `ref` 預設 `date.today()`；`run_checks(as_of=None)` 將 `as_of`(預設今日)往下傳給 `check_item(..., as_of)`、`_in_summary(..., as_of)`、`_summary_overdue(..., as_of)`,一律以 `as_of` 取代 today。顯式參數(非全域/contextvar)以避免 `_handle_daily` 多執行緒併發時互相污染。`build_daily_messages_for_user(uid, role, as_of=None)` 透傳。

**2. datetimepicker 入口 + gateway 擷取 params**
今日提醒(及 someday)輸出**追加**一顆按鈕：
```json
{"type":"datetimepicker","label":"📅 查其他日期","data":"o=someday","mode":"date","initial":"<today>","min":"<today-365>","max":"<today+365>"}
```
選定日期由 LINE 放在 postback 的 **`params.date`**(不在 `data`)。故 `gateway/line_gateway.py` webhook 需把 `event["postback"]["params"]` 一併轉發(現只轉 `data` 解析結果)。`agents/customer_service._process_postback` 遇 `o=someday` 讀 `params.date`→ 解析為 `date`→ `_handle_daily(uid, reply_token, as_of=選定日)`；缺值/格式錯→回退今日或提示。

**3. 投影語意(非歷史快照)**
Trello 無歷史,someday 用**目前**完成/清單狀態,重新以選定日的日曆評估日期條件。標頭顯示選定日 + 「依目前進度推算」以免誤解為歷史真相。

**4. 唯讀**
someday 內容 `show_buttons=False`(不放 ✅完成)；對非當日投影按完成語意混淆。今日提醒維持既有依角色顯示按鈕。

**5. 空內容仍給入口**
選定日無提醒時,回覆仍含「📅 查其他日期」按鈕(與「今日無提醒」一起),讓使用者可再選其他日。

## Risks / Trade-offs

- [投影非歷史,使用者可能誤解] → 標頭明示「依目前進度推算」。
- [多執行緒併發 someday] → 用顯式 `as_of` 參數,不用全域。
- [日期範圍過大失去意義] → datetimepicker `min/max` 限 ±365 天。
- [gateway 轉發 params 影響既有 postback] → 只新增欄位,既有 `o=complete/confirm/...` 不受影響。
