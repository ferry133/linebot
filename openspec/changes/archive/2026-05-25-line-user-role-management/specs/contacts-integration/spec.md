## MODIFIED Requirements

### Requirement: contacts data source
`trello_line_notifier.py` 的 `load_contacts()` SHALL 從 `line_users` DB table 讀取，回傳 `{name_lower: line_id}` 格式（與現有呼叫方簽名相容）。contacts.json 不再作為主要資料來源。

#### Scenario: Load contacts from DB
- **WHEN** trello-notifier CronJob 執行通知邏輯
- **THEN** `load_contacts()` 查詢 `line_users` WHERE role IN ('admin','employee','vendor','customer')
- **THEN** 回傳 `{display_name.lower(): line_id}` dict

#### Scenario: DB unavailable
- **WHEN** DB 連線失敗
- **THEN** `load_contacts()` 回傳空 dict 並記錄 error log
- **THEN** CronJob 繼續執行但不發送通知（不 crash）

## ADDED Requirements

### Requirement: contacts.json migration
系統 SHALL 提供一次性 migration script，將 contacts.json 的現有資料 upsert 進 `line_users` table。

#### Scenario: Migrate employee contacts
- **WHEN** 執行 migration script
- **THEN** contacts.json 中 projects="*" 的聯絡人以 role=employee 寫入 DB
- **THEN** contacts.json 中 projects=[...] 的聯絡人以 role=customer 寫入 DB
- **THEN** 已存在的 DB 記錄不被覆蓋（ON CONFLICT DO NOTHING）
