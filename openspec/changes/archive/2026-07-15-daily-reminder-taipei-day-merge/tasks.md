## 1. 台北基準日

- [x] 1.1 新增 `today_tw()`（`datetime.now(TAIPEI).date()`）於 `trello_line_notifier.py`
- [x] 1.2 `days_diff()` ref 預設、`run_checks()`、`build_daily_messages_for_user()`、`build_future_messages_for_user()` 改用 `today_tw()`

## 2. 單日工項合併 + 文案

- [x] 2.1 `check_item()`：`start == end` 時合併開始/到期為一筆（今天：`今天{（HH:MM）}開始＆到期`；倒數：`N 天後開始＆到期`；已完成回退 #1/#2；逾期不合併）
- [x] 2.2 #2/#4 當日文案改「今天開始」「今天{（HH:MM）}到期」

## 3. 驗證

- [x] 3.1 單元驗證 `check_item()`：單日今天/單日+3天/已完成單日/跨日開始/跨日到期/逾期 六情境輸出正確
- [x] 3.2 模擬 UTC 前一日環境（mock 系統時鐘或直接驗 `today_tw()` 與 `date.today()` 不同時判定仍正確）
- [x] 3.3 跑現有相關測試/煙囪驗證 `build_daily_messages_for_user()` 正常組 Flex
