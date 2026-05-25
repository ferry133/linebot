## Context

目前系統使用 NAS 上的 `contacts.json` 靜態檔案管理聯絡人與權限，格式為 `{name: {line_id, projects}}`。系統已有：
- PostgreSQL DB（`working_memory`、`knowledge`、`episodes`、`trello_boards` tables）
- `linebot-admin` Web UI（Flask，Basic Auth，CRUD contacts.json）
- `customer_service.py` 的 `_get_allowed_boards()` 從 contacts.json 讀取權限
- `trello_line_notifier.py` 的 `load_contacts()` 從 contacts.json 讀取 LINE ID

問題：contacts.json 需手動維護、無法自動記錄新用戶、無角色語意、trello-notifier 與 linebot 各自維護不同來源。

## Goals / Non-Goals

**Goals:**
- 用戶首次傳訊息時自動建檔（LINE ID + 顯示名稱 + 大頭貼），角色預設 visitor
- 五種角色：`admin`、`employee`（員工）、`vendor`（合作廠商）、`customer`（客戶）、`visitor`
- admin/employee 可透過管理介面升級角色並指派可存取專案
- trello-notifier 改從 DB 讀取 LINE ID，contacts.json 保留用於初始資料遷移
- 管理 Web UI 擴充支援用戶列表、角色管理、專案指派

**Non-Goals:**
- LINE Login OAuth 流程（本設計使用 Webhook 自動建檔，非 LINE Login）
- 細粒度的 API 權限控制（只做 Trello 專案層級的存取控制）
- 多租戶（目前只服務意念情境一個公司）

## Decisions

### D1: 儲存層 — DB table 取代 contacts.json

**選擇**：新增 `line_users` table，contacts.json 僅用於初始資料遷移後棄用。

**理由**：
- 自動建檔需要即時寫入，檔案 I/O 在多 Pod 環境下有競爭問題
- DB 支援查詢（依角色篩選、依專案篩選），檔案不支援
- 已有 PostgreSQL，不新增依賴

**Table Schema**：
```sql
CREATE TABLE line_users (
    line_id      TEXT PRIMARY KEY,
    display_name TEXT,
    picture_url  TEXT,
    role         TEXT NOT NULL DEFAULT 'visitor',
    projects     JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);
-- projects 欄位：role='admin'/'employee' 時忽略（存取全部）
-- projects 欄位：role='vendor'/'customer' 時為可存取的 Trello 看板名稱清單
-- projects 欄位：role='visitor' 時為空陣列（無存取權限）
```

**淘汰的替代方案**：擴充 contacts.json 格式 → 多 Pod 寫入衝突、無法自動建檔。

### D2: 自動建檔觸發點 — line-gateway

**選擇**：在 `gateway/line_gateway.py` 收到訊息後，publish MQTT 前先確保用戶存在於 DB（upsert display_name/picture_url，不覆蓋已設定的 role）。

**理由**：
- Gateway 是所有訊息的唯一入口點，集中處理避免重複邏輯
- 呼叫 LINE Profile API 是 I/O 操作，放在 gateway 可非同步處理

**LINE Profile API**：`GET https://api.line.me/v2/bot/profile/{userId}`，回傳 `displayName`、`pictureUrl`。

**淘汰的替代方案**：在 customer_service_agent 建檔 → 需透過 MQTT 繞一圈，延遲較高。

### D3: 權限查詢 — 統一從 DB 讀取

**選擇**：`customer_service.py` 的 `_get_allowed_boards()` 改查 `line_users` table；`trello_line_notifier.py` 的 `load_contacts()` 改查 DB。

**角色 → 存取規則**：
| 角色 | allowed_boards |
|------|---------------|
| admin | None（無限制） |
| employee | None（無限制） |
| vendor | projects 欄位的看板清單 |
| customer | projects 欄位的看板清單 |
| visitor | []（封鎖，回覆「請聯繫服務人員」） |

### D4: 管理介面 — 擴充現有 linebot-admin

**選擇**：在現有 Flask admin_server.py 加入用戶管理路由，不另起服務。

**新增路由**：
- `GET /api/users` — 列出所有用戶（依角色篩選）
- `PUT /api/users/<line_id>` — 更新角色與專案
- 現有 `/api/contacts` 路由保留（遷移過渡期），但改為從 DB 讀取

### D5: contacts.json 遷移策略

**選擇**：一次性 migration job，將 contacts.json 的資料 upsert 進 DB，完成後 contacts.json 停止使用。

**遷移邏輯**：
- contacts.json 的 `projects: "*"` → role `employee`
- contacts.json 的 `projects: [...]` → role `customer`，projects 欄位填入清單
- 已存在的 DB 記錄不覆蓋（保留已設定的 role）

## Risks / Trade-offs

- **LINE Profile API 失敗** → Mitigation：建檔失敗時靜默略過（用 line_id 只填 PRIMARY KEY，display_name 為 null），不阻斷訊息處理
- **DB 連線中斷時 gateway 建檔失敗** → Mitigation：gateway 建檔用 try/except 包住，失敗不影響訊息轉發
- **contacts.json 遷移資料不完整** → Mitigation：遷移後保留 contacts.json 唯讀備份 30 天，發現問題可手動補錄
- **trello-notifier CronJob 改用 DB 後，DB 不可用時通知失敗** → Mitigation：`load_contacts()` 加 fallback 回傳空 dict 並 log error，不 crash

## Migration Plan

1. 執行 DB migration：新增 `line_users` table（`migrations/003_line_users.sql`）
2. 執行一次性 migration job：從 contacts.json upsert 進 DB（`agents/migrate_contacts.py`）
3. 部署新版 image（含所有 code 變更）
4. 驗證：管理介面可列出用戶、trello-notifier 通知正常、新用戶互動後自動建檔
5. 舊 contacts.json 保留在 NAS 作為備份，不刪除

**Rollback**：若 DB 查詢有問題，`_get_allowed_boards()` 加 fallback：DB 失敗時回傳 None（無限制），確保服務不中斷。

## Open Questions

- LINE Profile API 是否對群組訊息的 userId 也有效？（目前只處理 1-on-1 訊息）
- `visitor` 角色是否需要回覆引導訊息，還是完全靜默？（目前設計為回覆「請聯繫服務人員」）
