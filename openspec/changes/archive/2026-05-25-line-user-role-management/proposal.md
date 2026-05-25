## Why

目前系統對所有 LINE 用戶一視同仁，沒有角色區分，導致客戶可能看到不屬於自己的工程資料，且新用戶首次互動後無法自動識別身分。需要一套完整的 LINE 用戶身分管理與權限控制機制，讓不同角色（admin、員工、合作廠商、客戶、visitor）只能存取其被授權的專案資訊。

## What Changes

- **新增** LINE 用戶自動建檔：用戶首次傳訊息時，自動記錄 LINE ID、顯示名稱、大頭貼，初始角色設為 `visitor`
- **新增** 五種角色定義：`admin`、`員工`、`合作廠商`、`客戶`、`visitor`，各有不同的資料存取權限
- **新增** 角色升級流程：admin/員工 可透過管理介面將 visitor 升級為合作廠商或客戶，並指定可存取的專案
- **修改** 管理 Web UI（`linebot-admin`）：擴充為完整的 LINE 用戶管理介面，支援角色設定與專案權限指派
- **修改** `contacts.json` → PostgreSQL `line_users` table：從檔案改為 DB，支援自動建檔與即時更新
- **修改** `trello-notifier` 整合：沿用同一份 DB，通知系統從 DB 讀取聯絡人 LINE ID

## Capabilities

### New Capabilities

- `line-user-registry`: 自動記錄首次互動的 LINE 用戶基本資料（LINE ID、名稱、大頭貼），初始角色 visitor
- `role-based-access-control`: 五種角色定義與對應的 Trello 專案存取權限控制
- `user-management-ui`: 管理介面支援查看所有用戶、升級角色、指派可存取專案

### Modified Capabilities

- `contacts-integration`: `contacts.json` 遷移至 DB `line_users` table，trello-notifier 改從 DB 讀取，現有員工資料需遷移

## Impact

- **新增 DB table**：`line_users`（LINE ID、名稱、大頭貼、角色、可存取專案清單、建立時間）
- **修改**：`agents/customer_service.py` — 用戶首次互動時呼叫 LINE Profile API 建檔，權限查詢改讀 DB
- **修改**：`agents/admin_server.py` — 擴充為用戶管理介面
- **修改**：`trello_line_notifier.py` — `load_contacts()` 改從 DB 讀取
- **移除依賴**：`contacts.json`（由 DB 取代，舊檔保留用於初始資料遷移）
- **新增依賴**：LINE Messaging API Profile endpoint（`/v2/bot/profile/{userId}`）
