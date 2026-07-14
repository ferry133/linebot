# Design: daily-reminder-taipei-day-merge

## Context

- pod（gateway / agents / CronJob）系統時區為 UTC；`trello_line_notifier.py` 用 `date.today()` 作為 #1–#9 的基準日。CronJob 08:00 Asia/Taipei（= 00:00 UTC）跑批次時剛好同日、不出錯；但 **on-demand 拉取**（Rich Menu「今日提醒」）在台北 00:00–07:59 觸發時 UTC 還是前一天 → 今天的工項顯示「1 天後開始」「1 天內到期」。
- 單日工項（`[@(x),20260714-20260714:1300]`）同時命中 #2 今日開始與 #4 今日到期（或倒數期間 #1+#3），同卡出現兩則重複區塊。
- 檔內已有 `TAIPEI = ZoneInfo("Asia/Taipei")`（`trello_line_notifier.py:13`）。

## Goals / Non-Goals

**Goals:**
- 「今天」一律以 Asia/Taipei 計，任何時刻拉取結果一致。
- 單日工項一則合併提醒；當日文案「今天開始＆到期」。
- 「今日開始」「今日到期」文案改「今天開始」「今天到期」。

**Non-Goals:**
- 不改觸發條件語意（窗口 ±7、完成抑制、RBAC、收件人規則不變）。
- 不改 someday / future 的選定日投影邏輯（只改「預設今天」的取得方式）。
- 不動 legacy `linebot_server.py`（未部署）。

## Decisions

1. **新增 `today_tw()` helper**：`datetime.now(TAIPEI).date()`；`days_diff()` 的 `ref` 預設、`run_checks(as_of=None)`、`build_daily_messages_for_user()`、`build_future_messages_for_user()` 內的 `date.today()` 全數改用。
   - 替代方案：在 k8s manifest 設 `TZ=Asia/Taipei`。否決——需動 jg-base 多個 workload、且程式仍隱性依賴環境；程式內明確化較穩。
2. **合併判定放在 `check_item()`**：`start == end`（同一天）時，開始側與到期側合併出一筆，**不再**分別觸發 #1/#2 與 #3/#4：
   - `dd == 0` 且未完成 → `今天{（HH:MM）}開始＆到期`，色 `#D32F2F`，收件人 = sponsors ∪ internal（沿用 #4 到期側）。
   - `1 ≤ dd ≤ 7` 且未完成 → `{dd} 天後開始＆到期`，色 `_due_color(dd)`（取較急迫的到期色）。
   - **已完成**的單日工項：到期側本被抑制（`active=False`），為避免合併後反而多發，開始側回退為原 #1/#2 行為（僅 sponsors、開始文案）。
   - 逾期（`dd < 0`）不合併——開始已成過去，維持 #6 `已逾期 N 天`。
3. **文案**：#2 → `今天開始`；#4 → `今天{（HH:MM）}到期`。rec[9]=label 去重鍵不變。

## Risks / Trade-offs

- [合併後 label 顏色/收件人取到期側] 開始側原本只給 sponsors；聯集後 internal 也會看到單日工項的開始資訊 → 可接受，internal 本來就會收到同卡 #4。
- [someday 傳入 as_of 路徑] 不受影響（`ref or …` 短路），以測試覆蓋確認。
- [快取] `_scan_boards()` 45s TTL 與日期無關，無跨日快取污染風險。

## Migration Plan

一般 release 流程：merge main → CI build image → jg-base bump sha → flux reconcile。無資料遷移；回滾即回退 image。
