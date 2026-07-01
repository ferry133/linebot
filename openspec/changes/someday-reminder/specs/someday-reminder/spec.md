## ADDED Requirements

### Requirement: 以 datetimepicker 指定過去/未來日期拉取提醒
系統 SHALL 讓使用者透過 **LINE datetimepicker（`mode=date`）按鈕**選擇一個過去或未來日期,拉取以該日為基準計算的提醒內容,並以 **Reply API（免費）**回覆。此入口 SHALL 對**所有角色**(admin/employee/vendor/customer)開放;各角色可見範圍**沿用既有 RBAC**,MUST NOT 因此擴大或縮小。datetimepicker 的可選範圍 SHALL 限制在合理區間(建議今日 ±365 天)。

#### Scenario: 選定日期回覆該日提醒
- **WHEN** 使用者點 datetimepicker 按鈕並選一個日期(過去或未來)
- **THEN** 系統以該日為基準計算並 Reply 回覆對應提醒內容

#### Scenario: 各角色皆可用且範圍不變
- **WHEN** 任一角色(含 customer)使用指定日期入口
- **THEN** 回覆內容的可見範圍與其今日提醒相同(RBAC 不變),只是基準日改為選定日

### Requirement: 選定日以共用引擎重新評估日期條件
someday 提醒 SHALL 與今日提醒**共用內容引擎**,將所有日期相關判定(#1 開始倒數、#2 今日開始、#3 結束倒數、#4 今日到期、#5/#6 逾期、#7 停滯、#8 全完成、#9 進行中窗口)以**選定日**取代「今天」重新評估。完成狀態抑制、RBAC、去重、格式等其餘規則 MUST 維持不變。

#### Scenario: 未來日呈現屆時將到期/逾期者
- **WHEN** 選定未來日 D,某工項結束日落在 D 的到期/逾期判定內
- **THEN** 該工項以 D 為基準呈現於對應急迫度(如「今日到期」「已逾期 N 天」皆相對 D)

#### Scenario: 過去日以當時日曆呈現
- **WHEN** 選定過去日 D
- **THEN** 各工項的開始/到期/逾期/進行中窗口皆相對 D 判定

### Requirement: 投影語意與標頭揭示
由於 Trello 無歷史狀態,someday 提醒 SHALL 以**目前**各工項的完成/清單狀態為輸入,僅重新以選定日的日曆評估日期條件(即**投影/推算**,非歷史快照)。回覆標頭 SHALL 顯示**選定日期**並明示「依目前進度推算」,使 MUST NOT 被誤解為該日的歷史真相。

#### Scenario: 標頭顯示選定日與推算註記
- **WHEN** 回覆 someday 內容
- **THEN** 標頭含選定日期字樣與「依目前進度推算」註記,與今日提醒可區分

### Requirement: someday 內容唯讀
someday 提醒內容 MUST NOT 含「✅完成」等操作按鈕(對非當日投影按完成語意混淆);使用者要標記完成 SHALL 改用今日提醒。datetimepicker「查其他日期」按鈕本身不屬操作按鈕,不受此限。

#### Scenario: someday 不顯示完成按鈕
- **WHEN** 呈現 someday 提醒(任一角色)
- **THEN** 工項卡片不含 ✅完成 按鈕

### Requirement: 空內容與錯誤處理
選定日無任何提醒時,系統 SHALL 回覆可辨識的「該日無提醒」訊息,且仍附「📅 查其他日期」按鈕以便再選。datetimepicker 未帶日期或日期格式無法解析時,系統 MUST NOT 崩潰,SHALL 回退為今日內容或回覆可辨識提示。

#### Scenario: 選定日無提醒仍給入口
- **WHEN** 選定日計算後無任何內容
- **THEN** 回覆「該日無提醒」並含「查其他日期」按鈕

#### Scenario: 日期缺失或無法解析
- **WHEN** postback 未帶 `params.date` 或無法解析
- **THEN** 系統回退今日或回覆可辨識提示,不崩潰
