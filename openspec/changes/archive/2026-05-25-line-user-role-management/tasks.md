## 1. DB Migration

- [x] 1.1 建立 `migrations/003_line_users.sql`：CREATE TABLE line_users (line_id PK, display_name, picture_url, role DEFAULT 'visitor', projects JSONB DEFAULT '[]', created_at, updated_at)
- [x] 1.2 在 `jg-base` migration Job 的 ConfigMap 加入 `003_line_users.sql`，更新 Job name 為 `postgres-migrate-v3`
- [x] 1.3 執行 migration Job 確認 table 建立成功

## 2. 聯絡人資料遷移

- [x] 2.1 建立 `agents/migrate_contacts.py`：讀 `/app/knowledge/contacts.json`，upsert 進 `line_users`（projects="*" → role=employee，projects=[...] → role=customer）
- [x] 2.2 在 jg-base 加入一次性 Job manifest，執行 migrate_contacts.py
- [x] 2.3 確認 DB 中有正確的用戶資料後，將 contacts.json 標記為唯讀備份

## 3. LINE 用戶自動建檔

- [x] 3.1 修改 `gateway/line_gateway.py`：收到訊息後，非同步呼叫 LINE Profile API（`GET /v2/bot/profile/{userId}`）並 upsert `line_users`
- [x] 3.2 實作 upsert 邏輯：INSERT … ON CONFLICT (line_id) DO UPDATE SET display_name, picture_url, updated_at（不覆蓋 role/projects）
- [x] 3.3 LINE Profile API 失敗時只記錄 warning，不阻斷訊息轉發

## 4. 權限查詢改讀 DB

- [x] 4.1 修改 `agents/customer_service.py` 的 `_get_allowed_boards(user_id)`：改查 `line_users` table，依 role 回傳 None/list/[]
- [x] 4.2 移除 `_load_user_permissions()` 讀 contacts.json 的邏輯
- [x] 4.3 `trello_line_notifier.py` 的 `load_contacts()` 改查 DB：SELECT line_id, display_name FROM line_users WHERE role IN ('admin','employee','vendor','customer')

## 5. 管理 Web UI 擴充

- [x] 5.1 `agents/admin_server.py` 新增 `GET /api/users`：從 `line_users` 查詢，支援 `?role=` 篩選參數
- [x] 5.2 新增 `PUT /api/users/<line_id>`：更新 role 與 projects（employee 不可設 admin role）
- [x] 5.3 更新前端 HTML：加入「用戶管理」分頁，顯示大頭貼縮圖、顯示名稱、角色 badge、建立時間
- [x] 5.4 編輯對話框：角色下拉選單（visitor/vendor/customer，employee 登入時不顯示 admin），專案勾選清單從 trello_boards 拉取
- [x] 5.5 保留現有 `/api/contacts` CRUD 路由供過渡期使用（內部改從 DB 讀寫）

## 6. 測試與驗證

- [x] 6.1 build & push 新 image，rollout restart 所有 linebot deployments
- [x] 6.2 驗證：傳訊息給 bot → 確認 `line_users` 有新記錄，role=visitor
- [x] 6.3 驗證：管理介面可列出用戶，升級 visitor → customer 並指派專案
- [x] 6.4 驗證：升級後該用戶查詢 Trello 只看到指定看板
- [x] 6.5 驗證：trello-notifier morning CronJob 正常發送通知（從 DB 讀聯絡人）
- [x] 6.6 驗證：visitor 用戶查詢工程進度 → 收到無權限訊息
