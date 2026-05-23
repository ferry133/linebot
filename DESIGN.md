# 意念情境室內裝修 — LINE 客服系統設計文件

## 1. 系統概覽

兩大功能，共用同一個 Docker image，由 k8s workload 的 `command` 決定執行模式。

| 功能 | 方向 | 說明 |
|------|------|------|
| 客服 Bot | 雙向 | 客戶透過 LINE 詢問 → Claude AI 理解並查詢 Trello → 即時回覆 |
| 定時通知 | 單向 | CronJob 掃描 Trello，依九項觸發條件推播工程提醒給客戶與內部人員 |

---

## 2. 整體架構

```
客戶 LINE
    │  POST /webhook
    ▼
LINE Platform
    │  POST /webhook
    ▼
┌─────────────────────────────────────────────────────┐
│ k8s cluster (linebot namespace)                     │
│                                                     │
│  line-gateway (Flask)                               │
│  ├─ HMAC-SHA256 驗簽                                │
│  ├─ 立即回 200（避免 LINE 10s timeout 重送）         │
│  └─ MQTT publish → agents/customer_service/inbox    │
│           │                                         │
│           ▼  MQTT (mosquitto)                       │
│  customer-service-agent                             │
│  ├─ 五步循環 (Perceive→Recall→Reason+Act→Reflect)   │
│  ├─ Claude API (claude-haiku-4-5)                   │
│  ├─ MQTT request → trello-agent → MQTT reply        │
│  └─ MQTT publish → gateway/outbox                   │
│           │                                         │
│           ▼                                         │
│  line-gateway → LINE Push API → 客戶                │
│                                                     │
│  trello-agent                                       │
│  ├─ 訂閱 agents/trello/requests                     │
│  ├─ 查詢 Trello API（含 60s cache）                  │
│  └─ 依 allowed_boards 過濾後回覆                    │
│                                                     │
│  linebot-admin (Flask)                              │
│  └─ 管理 contacts.json（聯絡人/權限）                │
└─────────────────────────────────────────────────────┘
    │
    ▼ NFS mount
NAS1:/volume2/knowledge/
    ├─ contacts.json
    ├─ project_photos.yaml
    └─ *.md (知識庫)

    ▼ PostgreSQL (db namespace)
    ├─ working_memory  (對話記憶)
    ├─ knowledge       (語意記憶)
    ├─ episodes        (情節記憶)
    └─ trello_boards   (看板 ID ↔ 名稱快取)
```

---

## 3. Agent 設計

### 3.1 五步循環（customer-service-agent）

```
Perceive  → 將用戶訊息轉為 situation 字串
Recall    → 從 DB 查詢相關 knowledge + episodes
Reason    → Claude API，帶入 system prompt + 記憶 context + 對話歷史
Act       → 執行工具（query_trello / get_project_photos / escalate_to_manager）
Reflect   → 評估回答品質，寫入 episodes；若品質高，萃取 knowledge
```

### 3.2 工具定義

| 工具 | 觸發時機 | 動作 |
|------|---------|------|
| `query_trello` | 詢問工程進度/排程/逾期 | MQTT request → trello-agent → 回傳工項清單 |
| `get_project_photos` | 詢問工地照片 | 讀 project_photos.yaml → 回傳 Synology Photos 連結 |
| `escalate_to_manager` | 無法確定/需人工判斷 | LINE Push 到管理群組或 SA/Larry |

### 3.3 MQTT 訊息格式

**customer-service → trello-agent（request）**
```json
{
  "request_id": "uuid",
  "reply_to": "agents/trello/responses/{uuid}",
  "query_type": "all | overdue | upcoming | specific",
  "keyword": "搜尋關鍵字（query_type=specific 時使用）",
  "allowed_boards": null
}
```
- `allowed_boards: null` → 不過濾（員工）
- `allowed_boards: ["看板名稱"]` → 只回傳指定看板的工項
- `allowed_boards: []` → 返回無權限訊息

**customer-service → gateway（outbox）**
```json
{
  "user_id": "LINE user_id",
  "content": "回覆文字"
}
```

### 3.4 三層記憶

| 層 | DB Table | 說明 | 生命週期 |
|----|----------|------|----------|
| 工作記憶 | `working_memory` | 對話訊息陣列（per user_id） | 對話期間 |
| 語意記憶 | `knowledge` | fact + confidence + source_count | 持久，累積學習 |
| 情節記憶 | `episodes` | situation/action/result/quality | 持久，經驗回顧 |

---

## 4. 知識庫設計

### 4.1 NAS 目錄結構

```
NAS1:/volume2/knowledge/
├── contacts.json          # 聯絡人 & 權限（唯一真相來源）
├── project_photos.yaml    # 工地相簿連結
├── 01_service_process.md  # 服務流程
├── 02_construction_steps.md
├── 03_pricing.md
├── 04_design_vs_turnkey.md
├── 05_contract_guide.md
└── 06_inspection_guide.md
```

所有 `.md` 檔在 agent 啟動時自動載入為 system prompt 的「室內裝修知識庫」區塊。

### 4.2 contacts.json 格式

```json
{
  "Larry": {
    "line_id": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "projects": "*"
  },
  "王小明": {
    "line_id": "Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "projects": ["王小明_信義路三段"]
  }
}
```

| `projects` | 意義 |
|------------|------|
| `"*"` | 員工/管理員，可查詢所有工地 |
| `["看板名稱"]` | 客戶，只能查詢指定看板 |
| 未列出此 LINE ID | 無查詢權限 |

### 4.3 project_photos.yaml 格式

```yaml
王小明_信義路三段: https://your-nas.synology.me/photo/mo/sharing/xxxxxx
陳大明_大安區: https://your-nas.synology.me/photo/mo/sharing/yyyyyy
```

---

## 5. 權限控制流程

```
LINE 用戶發訊息
    │
    ▼
customer-service-agent._get_allowed_boards(user_id)
    │
    ├─ 讀 contacts.json
    ├─ projects == "*"  → allowed_boards = None（不過濾）
    ├─ projects == list → allowed_boards = ["看板A", "看板B"]
    └─ 未列出           → allowed_boards = []（拒絕）
    │
    ▼ MQTT request（帶 allowed_boards）
trello-agent._query()
    │
    ├─ _scan_all_items()  ← 全量 cache（60s TTL，所有用戶共享）
    │
    └─ allowed_boards 過濾（cache 取出後）
           │
           ├─ None → 不過濾，回傳全部
           ├─ []   → 空結果（不應到達此處，已在 customer-service 攔截）
           └─ list → 保留 board 名稱包含任一 allowed 字串的工項
```

---

## 6. K8s 部署架構

### 6.1 linebot namespace

| 資源 | 類型 | 說明 |
|------|------|------|
| `line-gateway` | Deployment | Flask webhook + LINE Push API，port 8080 |
| `customer-service-agent` | Deployment | Claude agentic loop，mount knowledge PVC |
| `trello-agent` | Deployment | Trello 查詢，MQTT request/reply |
| `linebot-admin` | Deployment | 管理 Web UI，port 8081，mount knowledge PVC |
| `trello-board-sync` | CronJob | 每日 03:00 UTC+8，同步 Trello boards → DB |
| `trello-notifier-morning/noon/evening` | CronJob | 定時通知，mount knowledge PVC |
| `linebot-knowledge-nas` | PVC | NFS mount NAS1:/volume2/knowledge（ReadOnlyMany） |

### 6.2 db namespace

| 資源 | 類型 | 說明 |
|------|------|------|
| `postgres` | Deployment | PostgreSQL 16 |
| `postgres-backup` | CronJob | 每日 02:00 UTC+8，pg_dump → NAS1:/volume2/backup1 |
| `postgres-backup-nas` | PVC | NFS mount NAS1:/volume2/backup1 |

### 6.3 對外路由

| 服務 | Gateway | URL | 說明 |
|------|---------|-----|------|
| `line-gateway` | envoy-external | `linebot.jiahd.cc/webhook` | LINE webhook，需公網 |
| `linebot-admin` | envoy-internal | `linebot-admin.jiahd.cc` | 管理介面，內網限定 |

---

## 7. 維護 SOP

### 新增客戶
1. 取得客戶 LINE user_id（請客戶傳任意訊息後從 admin UI 的 log 取得，或客戶自行查詢）
2. 開啟 `https://linebot-admin.jiahd.cc`
3. 點「新增聯絡人」，填姓名 / LINE ID，選「客戶（指定工地）」，勾選對應看板
4. 儲存 → 立即生效，無需重啟 Pod

### 新增/更新知識庫
1. 在 NAS `knowledge/` 資料夾新增或編輯 `.md` 檔
2. 重啟 customer-service-agent Pod：`kubectl -n linebot rollout restart deployment/customer-service-agent`

### 新增工地相簿
1. 在 Synology Photos 建立工地相簿，產生共享連結
2. 編輯 NAS `knowledge/project_photos.yaml`，加入一行：
   ```yaml
   王小明_信義路: https://...synology.me/photo/mo/sharing/xxxxxx
   ```
3. 無需重啟（`get_project_photos` 每次呼叫時即時讀檔）

### 更新 Trello 看板清單（通常自動）
- 每日 03:00 UTC+8 由 `trello-board-sync` CronJob 自動同步
- 手動觸發：`kubectl -n linebot create job --from=cronjob/trello-board-sync manual-sync`

---

## 8. 環境變數

| 變數 | 使用方 | 說明 |
|------|--------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | gateway, notifier | LINE Messaging API |
| `LINE_CHANNEL_SECRET` | gateway | Webhook 驗簽 |
| `LINE_NOTIFY_GROUP_ID` | customer-service | escalate 推播目標群組 |
| `ANTHROPIC_API_KEY` | customer-service | Claude API |
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | trello-agent, notifier, board-sync | Trello API |
| `DATABASE_URL` | customer-service, trello-agent, admin | PostgreSQL 連線字串 |
| `MQTT_HOST` | gateway, agents | mosquitto 服務位址 |
| `ADMIN_USER` / `ADMIN_PASS` | admin | Web UI 登入帳密 |
