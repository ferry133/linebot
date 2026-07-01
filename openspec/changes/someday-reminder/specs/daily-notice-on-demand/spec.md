## ADDED Requirements

### Requirement: 提供指定日期(someday)入口按鈕
每日內容(今日提醒與 someday 回覆)的輸出 SHALL 追加一顆 **LINE datetimepicker（`mode=date`）按鈕**「📅 查其他日期」,作為 someday 提醒的入口(`data=o=someday`,選定日經 `params.date` 回傳)。內容為空時(今日/該日無提醒)MUST 仍附此按鈕,使使用者可持續切換日期。此按鈕不屬「✅完成」類操作按鈕,不受角色操作按鈕顯示規則限制。

#### Scenario: 今日提醒含查其他日期按鈕
- **WHEN** 使用者拉取今日提醒(任一角色)
- **THEN** 輸出含「📅 查其他日期」datetimepicker 按鈕

#### Scenario: 空內容仍含入口按鈕
- **WHEN** 今日或選定日無任何提醒
- **THEN** 回覆仍含「📅 查其他日期」按鈕
