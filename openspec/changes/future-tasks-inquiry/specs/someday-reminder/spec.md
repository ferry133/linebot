## MODIFIED Requirements

### Requirement: 以 datetimepicker 指定過去/未來日期拉取提醒
系統 SHALL 讓使用者透過**「未來工項」回覆內的「📅 指定日期」quick-reply（datetimepicker，`mode=date`，`data=o=someday`）**選擇一個過去或未來日期,拉取以該日為基準計算的提醒內容,並以 **Reply API（免費）**回覆。此入口 SHALL 對**所有角色**(admin/employee/vendor/customer)開放;各角色可見範圍**沿用既有 RBAC**,MUST NOT 因此擴大或縮小。選定日經 postback 的 `params.date` 回傳;引擎、投影與唯讀規則不變。單日 datetimepicker **不再**佔 Rich Menu 一級入口(見 `daily-notice-on-demand`、`future-tasks-inquiry`)。

#### Scenario: 由指定日期 quick-reply 回覆該日提醒
- **WHEN** 使用者於「未來工項」回覆點「📅 指定日期」並選一個日期(過去或未來)
- **THEN** 系統以該日為基準計算並 Reply 回覆對應提醒內容

#### Scenario: 各角色皆可用且範圍不變
- **WHEN** 任一角色(含 customer)使用指定日期入口
- **THEN** 回覆內容的可見範圍與其今日提醒相同(RBAC 不變),只是基準日改為選定日
