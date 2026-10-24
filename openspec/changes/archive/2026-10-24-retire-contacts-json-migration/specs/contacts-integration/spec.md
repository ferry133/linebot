## MODIFIED Requirements

### Requirement: contacts data source
`trello_line_notifier.py` 的 `load_contacts()` SHALL 從 `line_users` DB table 讀取，回傳 `{name_lower: line_id}` 格式（與現有呼叫方簽名相容）。contacts.json 不再作為主要資料來源，也不會被同步進 `line_users`；它只在 DB 讀取失敗時作為唯讀退路。

#### Scenario: Load contacts from DB
- **WHEN** trello-notifier CronJob 執行通知邏輯
- **THEN** `load_contacts()` 查詢 `line_users` WHERE role IN ('admin','employee','vendor','customer')
- **THEN** 回傳 `{display_name.lower(): line_id}` dict

#### Scenario: DB unavailable
- **WHEN** DB 連線或查詢失敗
- **THEN** `load_contacts()` 記錄 warning log，改為直接讀取 `knowledge/contacts.json`（唯讀，不寫回 DB）
- **THEN** contacts.json 不存在或無法讀取時回傳空 dict
- **THEN** CronJob 繼續執行（不 crash）

## REMOVED Requirements

### Requirement: contacts.json migration
**Reason**: `line_users` 已是聯絡人與權限的主要來源（gateway 自動建檔、admin UI 維護）。執行此遷移的 `linebot-migrate-contacts-v1` Job 因 Flux 重建而約每小時重跑，會把 DB 已刪除的使用者從 contacts.json 插回；jg-extras 移除該 Job（ferry133/jg-extras#12）。
**Migration**: 新增或修改聯絡人一律走 admin UI（或使用者首次傳訊時由 gateway 自動建檔）。寫進 contacts.json 不再會出現在 `line_users`。`agents/migrate_contacts.py` 暫留，待 Job 移除後另行刪除。
