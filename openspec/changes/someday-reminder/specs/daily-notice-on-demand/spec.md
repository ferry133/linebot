## ADDED Requirements

### Requirement: Rich Menu 提供指定日期(someday)入口
Rich Menu SHALL 提供一格「查其他日期」作為 someday 提醒入口,採 **LINE datetimepicker（`mode=date`，`data=o=someday`）**;選定日經 postback 的 `params.date` 回傳。此入口與「今日提醒」「使用說明」並列於同一 Rich Menu。datetimepicker 不設 `initial/min/max`（靜態 Rich Menu 無法持有動態日期），每次點按以當下今日為預設、可選過去/未來日。**每日內容本身 MUST NOT 再放 datetimepicker 按鈕**（入口統一由 Rich Menu 提供，避免重複）。

#### Scenario: Rich Menu 有查其他日期入口
- **WHEN** 使用者開啟 Rich Menu
- **THEN** 有「查其他日期」一格,點按彈出日期選擇器 → 選定日回傳 `o=someday` + `params.date`

#### Scenario: 每日內容不含日期選擇器按鈕
- **WHEN** 使用者拉取今日或 someday 內容
- **THEN** 內容中 MUST NOT 出現 datetimepicker 按鈕（入口在 Rich Menu）
