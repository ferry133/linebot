# Proposal: daily-reminder-taipei-day-merge

## Why

Pod 以 UTC 運行，日期判定用 `date.today()`：台北 00:00–07:59 之間拉「今日提醒」時 UTC 仍是前一天，導致**今天**開始/到期的工項顯示成「1 天後開始」「1 天內到期」（off-by-one）。另外單日工項（start == end）會同時觸發 #1/#2（開始）與 #3/#4（到期）兩則重複提醒，同一張卡在同一則每日內容出現兩次。

## What Changes

- 所有日期觸發判定（#1–#9）與 someday/future 的預設基準日，一律改以**台北時間（Asia/Taipei）的今天**計算，不再受 pod 系統時區影響。
- 單日工項（start == end）之「開始」與「到期」提醒**合併為一則**：
  - 當日：`今天開始＆到期`（有時間時 `今天（HH:MM）開始＆到期`）
  - 倒數（1–7 天）：`N 天後開始＆到期`
  - 合併後收件人為兩者聯集（sponsor + internal），且沿用「到期」側的完成抑制與顏色（較急迫者）。
- 當日文案由「今日開始」「今日到期」改為「**今天開始**」「**今天到期**」。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `consolidated-daily-notification`：新增基準日定義（Asia/Taipei）與單日工項合併提醒之要求；#2/#4 當日文案改為「今天開始」「今天到期」。

## Impact

- `trello_line_notifier.py`：`days_diff()`／`run_checks()`／`build_daily_messages_for_user()`／`build_future_messages_for_user()` 的今天基準；`check_item()` 的 #1–#4 觸發與文案。
- 下游共用者（customer_service `o=daily`、someday、future 視窗）自動繼承，無介面變更。
- 無 DB / API / 部署結構變更。
