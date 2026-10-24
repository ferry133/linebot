## Why

`line_users` 早已是聯絡人與權限的主要來源：使用者由 gateway 首次互動時自動建檔、或於 admin UI 建立/指派；`load_contacts()` 先讀 DB。然而 `contacts-integration` spec 仍保留「contacts.json migration」需求，DESIGN.md 也仍寫 contacts.json 是「唯一真相來源」、權限由它判定。

jg-extras 將移除 `linebot-migrate-contacts-v1` Job（ferry133/jg-extras#12）。該 Job 帶 `ttlSecondsAfterFinished: 600`，Flux 每次 reconcile 都重建，使「一次性遷移」實際約每小時跑一次（jg-extras#11），會把 DB 已刪除、但仍在 contacts.json 的使用者插回去。移除之後，spec 與文件應反映現況：contacts.json 不再同步進 `line_users`。

## What Changes

- **REMOVED** `contacts-integration` 的「contacts.json migration」需求：不再承諾 contacts.json → `line_users` 的同步。
- **MODIFIED** 「contacts data source」的「DB unavailable」情境，改為描述實際行為：DB 讀取失敗時退回直接讀 contacts.json（唯讀、不寫 DB），檔案不存在才回空 dict。原情境寫「回傳空 dict」與 `trello_line_notifier.py:162` 的程式碼不符。
- DESIGN.md：聯絡人/權限改述為以 DB（`line_users`、`line_user_projects`）為準；contacts.json 標為 legacy，只剩 notifier 的 DB 失敗退路會讀它。

## Non-goals

- 不刪除 `agents/migrate_contacts.py`：jg-extras#12 合併前，現役 image 的 Job 仍會執行它；刪除留待該 Job 移除後另行處理。
- 不移除 `load_contacts()` 的 contacts.json 退路。

## Capabilities

### Modified Capabilities
- `contacts-integration`: 移除 contacts.json migration 需求；修正 DB 不可用時的行為描述。

## Impact

- 僅 spec 與 DESIGN.md，無程式碼變更、無部署。
