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
│  └─ 管理 line_users / projects（聯絡人/權限）        │
└─────────────────────────────────────────────────────┘
    │
    ▼ NFS mount
NAS1:/volume2/knowledge/
    ├─ contacts.json   (legacy，僅 notifier DB 失敗退路)
    ├─ project_photos.yaml
    └─ *.md (知識庫)

    ▼ PostgreSQL (db namespace)
    ├─ working_memory  (對話記憶)
    ├─ knowledge       (語意記憶)
    ├─ episodes        (情節記憶)
    ├─ line_users / projects / line_user_projects  (聯絡人與權限)
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

#### Reason/Act 迴圈與 `max_tokens` 處理（重要）

`_reason_and_act()` 是一個最多 `MAX_TOOL_TURNS` 次的迴圈，每輪呼叫 Claude，
依 `stop_reason` 決定下一步：

| `stop_reason` | 處理 |
|---------------|------|
| `end_turn` | 正常結束，擷取 text block 為 `final_text`，跳出 |
| `max_tokens` | 答案被輸出上限截斷，**仍要擷取已生成的 text 為 `final_text`**，跳出 |
| `tool_use` | 執行工具、把結果接回 messages，續跑下一輪 |
| 其他 | 跳出 |

> ⚠️ **不要只認 `end_turn`。** 系統提示詞內嵌整個知識庫（約 2 萬字），Haiku
> 很容易產生超過 `max_tokens` 的長回覆，此時 `stop_reason == "max_tokens"`。
> 若只在 `end_turn` 時擷取文字，已生成的答案會被整個丟棄，`final_text` 留空，
> 於是 `_run()` 回傳 fallback「抱歉，目前無法處理您的問題，已通知專人跟進。」——
> 使用者會發現**每個需要長回覆的問題都被打回**。
>
> 配套：`MAX_TOKENS = 2048`（原為 1024，過低易截斷）。若仍常被截斷，可再調高。
>
> 除錯線索：log 的 `Reflected: quality=0.3` 即代表 `final_text` 為空
> （`_evaluate` 對長度 ≤20 的回覆給 0.3），表示落入上述情況。
>
> 修正提交：`70af92a`（2026-06-04）。

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
├── contacts.json          # legacy；聯絡人與權限已改存 DB（見 4.2）
├── project_photos.yaml    # 工地相簿連結
├── 01_service_process.md  # 服務流程
├── 02_construction_steps.md
├── 03_pricing.md
├── 04_design_vs_turnkey.md
├── 05_contract_guide.md
└── 06_inspection_guide.md
```

所有 `.md` 檔在 agent 啟動時自動載入為 system prompt 的「室內裝修知識庫」區塊。

### 4.2 聯絡人與權限（DB）

聯絡人與權限以 DB 為準，**不再讀 contacts.json**：

| Table | 內容 |
|-------|------|
| `line_users` | `line_id`、`display_name`、`alias_name`、`role`（admin / employee / vendor / customer / visitor） |
| `projects` | 專案（`trello_board_id`、`status`、對外標籤欄位） |
| `line_user_projects` | 使用者 ↔ 專案指派（customer 可見範圍） |

- **建檔**：使用者首次傳訊時 gateway 自動 upsert `line_users`；角色、alias、專案指派在 admin UI 維護。
- **contacts.json 為 legacy**：早期以 `agents/migrate_contacts.py` 一次性匯入 DB；執行它的 `linebot-migrate-contacts-v1` Job 已移除（ferry133/jg-extras#12），腳本本身也已刪除，**寫進 contacts.json 不會再出現在 `line_users`**。目前只有 `trello_line_notifier.load_contacts()` 在 DB 讀取失敗時會唯讀退回這個檔案。

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
customer-service-agent._get_user_role_and_projects(user_id)
    │
    ├─ 查 line_users.role；查無此人 → visitor
    └─ JOIN line_user_projects × projects（status='active' 且有 trello_board_id）
    │
    ▼ _get_user_auth → allowed_board_ids / owner_alias
    ├─ admin / employee → allowed_board_ids = None（不過濾）
    ├─ vendor           → allowed_board_ids = None + owner_alias = 自身 alias（只看被 [@(alias)] 標記的工項）
    ├─ customer         → allowed_board_ids = 指派看板的 board_id 清單
    └─ visitor          → allowed_board_ids = []（拒絕）
    │
    ▼ MQTT request（帶 allowed_board_ids + owner_alias）
trello-agent._query()
    │
    ├─ 全量 cache（60s TTL，所有用戶共享）
    └─ 依 board_id 與 owner_alias 過濾後回覆
```

> 權限一律從 `line_user_projects` JOIN `projects` 查，不得用 `line_users.projects` JSONB。詳見 spec `role-based-access-control`。

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
