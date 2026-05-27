## ADDED Requirements

### Requirement: Import dialog shows all NAS folders
匯入既有專案 dialog 的「NAS 資料夾」下拉 SHALL 列出 `00. 執行中案場/` 下所有資料夾，不過濾已被其他 project 引用者。提示文字 SHALL 改為說明可共用。

#### Scenario: List unfiltered folders
- **WHEN** admin 點選「匯入既有專案」
- **THEN** 下拉顯示 `00. 執行中案場/` 下所有資料夾（不論是否已被引用）
- **THEN** 提示文字「同一資料夾可被多個專案共用」

### Requirement: Import dialog accepts custom case_number
匯入既有專案 dialog SHALL 提供「案號」輸入欄（選填）。留空時提交，後端 auto-gen；有填時以該值作為案號。

#### Scenario: Custom case number on import
- **WHEN** admin 在匯入 dialog 填入 case_number = `115-001-王公館A`
- **THEN** 送出 POST body 含 `case_number: "115-001-王公館A"`
- **THEN** 後端以該值建立 project

#### Scenario: Empty case number on import
- **WHEN** admin 在匯入 dialog 留空 case_number 欄位
- **THEN** 送出 POST body 未含 case_number 或為空字串
- **THEN** 後端 auto-gen `{民國年}年第N案`

### Requirement: Archive warning when folder shared
當 admin 將 project 切到 archived，且該專案的 NAS 資料夾仍被其他 active project 引用時，UI SHALL 顯示提示訊息說明資料夾未實際搬移。

#### Scenario: Archive shared project shows warning
- **WHEN** archive 成功但 response 含 `nas_warning: "folder still in use"`
- **THEN** UI alert：「資料夾仍有其他進行中專案使用，本次不搬移實體資料夾」
