## Context

someday 用 `run_checks(as_of)` 對**單一日**投影觸發條件。區間清單需求不同:要列出「一段期間內會開始/到期的工項」,是**掃一次、依日期範圍收集**,而非逐日跑觸發。共用 `_scan_boards()`、`public_label`、RBAC 與投影揭示;新增一個區間收集器。

## Goals / Non-Goals

**Goals:** 未來/過去區間(2週/1月/2月/3月)工項清單、依日期排序、標開始/到期、RBAC 不變、唯讀、投影。保留單日 someday 為子入口。
**Non-Goals:** 不改今日提醒/每日 push/someday 單日引擎;不做歷史狀態還原。

## Decisions

**1. 區間收集器(新)**
`build_future_messages_for_user(user_id, role, direction, window)`：
- `direction ∈ {future, past}`、`window ∈ {2w,1m,2m,3m}`→ 天數 `{14,30,60,90}`。區間:future=`[今天, 今天+n]`、past=`[今天-n, 今天]`。
- `_scan_boards()` → 對每個**未完成、有 `[@]` tag** 的工項:`start` 落在區間 → 一筆「開始」事件;`end` 落在區間 → 一筆「到期」事件(同工項可各一)。
- 依事件**日期升序**排序;Flex 依日期分組(日期抬頭 + 該日事件行:`開始/到期 · public_label · 卡片/label`)。
- **RBAC**:supervisor 全部;vendor 僅自己 alias 被 tag;customer 僅其 `line_user_projects` 看板。沿用既有 `_get_user_auth`(allowed_board_ids + owner_alias)過濾。
- **唯讀**(無按鈕)、附「依目前進度推算」。空區間 → 「未來/過去 {視窗} 內無工項」。

**2. 互動(quick-reply)**
Rich Menu「未來工項」→ `postback o=future`(無參數=預設 future+1m)→ 回清單 + quick-reply:
- 未來：`o=future&dir=f&n=14|30|60|90`（2週/1月/2月/3月）
- 過去：`o=future&dir=p&n=14|30|60|90`
- 單日：`📅 指定日期` = **datetimepicker `o=someday`**（沿用既有單日投影,過去/未來）
`customer_service._process_postback` 收 `o=future` 讀 `dir`/`n` → `_handle_future`。

**3. Rich Menu**
中間格 label「未來工項」、action 由 datetimepicker(o=someday) 改 `postback o=future`;重繪底圖(月曆/時間軸圖示)、`setup_richmenu.py --replace` 重新部署。someday 單日入口移入 quick-reply。

## Risks / Trade-offs

- [quick-reply 數量]：未來4 + 過去4 + 指定日期 = 9(LINE 上限 13,OK)。
- [「1月」用 30 天近似]：以天數近似月,足夠總覽用途;標籤仍寫 2週/1月/2月/3月。
- [區間內工項很多 → Flex 過長]：依日期分組並限總筆數(如 上限 ~50 事件),超出提示縮小視窗。
