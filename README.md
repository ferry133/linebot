# linebot

意念情境室內裝修 — LINE 客服 Bot + 工程通知系統

## 功能概述

| 功能 | 模式 | 說明 |
|------|------|------|
| **客服 Bot** | 雙向 | 客戶透過 LINE 詢問問題 → Claude AI 查詢 Trello → 即時回覆；無法處理時推播管理群組 |
| **定時通知** | 單向 | CronJob 定時掃描 Trello，依九項條件推播工程提醒給客戶與內部人員 |

---

## 架構

```
客戶 LINE
    │
    ▼
LINE Platform ──POST /webhook──► line_gateway.py (Flask)
                                      │ MQTT publish
                                      ▼
                              agents/customer_service.py
                                      │ Claude Haiku + tools
                                      │  ├─ query_trello → agents/trello_agent.py
                                      │  └─ escalate_to_manager → LINE Push
                                      │ MQTT publish (reply)
                                      ▼
                              line_gateway.py ──LINE Push API──► 客戶

CronJob (morning/noon/evening)
    └─ trello_line_notifier.py ──LINE Push API──► 客戶 / SA / Larry

CronJob (daily)
    └─ agents/trello_board_sync.py ──► trello_boards (DB)

agents/admin_server.py (port 8081)
    └─ Web UI：聯絡人 / LINE 用戶 / 工程案管理
```

### k8s Workloads（linebot namespace）

| Workload | 類型 | Command |
|----------|------|---------|
| `line-gateway` | Deployment | `python /app/gateway/line_gateway.py` |
| `customer-service-agent` | Deployment | `python /app/agents/customer_service.py` |
| `trello-agent` | Deployment | `python /app/agents/trello_agent.py` |
| `linebot-admin` | Deployment | `python /app/agents/admin_server.py` (port 8081) |
| `trello-notifier-{morning,noon,evening}` | CronJob | `python /app/trello_line_notifier.py [morning\|noon\|evening]` |
| `trello-board-sync` | CronJob | `python /app/agents/trello_board_sync.py` |

同一個 Docker image，執行模式由 k8s workload 的 `command` 指定（無 `ENTRYPOINT`）。

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `gateway/line_gateway.py` | LINE Webhook 接收 + MQTT 橋接（純 I/O，無 AI 邏輯） |
| `agents/customer_service.py` | Claude AI 客服 Agent（五步循環：Perceive→Recall→Reason→Act→Reflect） |
| `agents/trello_agent.py` | Trello 查詢 Agent（by customer_service 呼叫） |
| `agents/admin_server.py` | 管理 Web UI：聯絡人、LINE 用戶 RBAC、工程案 CRUD、NAS 資料夾管理 |
| `agents/trello_board_sync.py` | 每日同步 Trello 看板清單至 DB |
| `trello_line_notifier.py` | 定時通知腳本（morning/noon/evening） |
| `shared/broker.py` | MQTT wrapper（paho-mqtt v2） |
| `shared/db.py` | PostgreSQL 連線池 + migration runner |
| `migrations/` | DB schema migrations（001–007） |
| `knowledge/contacts.json` | 聯絡人清單（掛載自 NAS） |
| `linebot_server.py` | 舊版單一 server（過渡期保留） |
| `Dockerfile` | 容器映像建置，推至 GHCR |
| `trello-line-design.md` | 九項通知觸發條件完整設計文件 |

---

## 環境變數

| 變數 | 用途 | 需要的 Workload |
|------|------|----------------|
| `ANTHROPIC_API_KEY` | Claude API 金鑰 | customer-service-agent |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API 金鑰 | line-gateway, trello-notifier |
| `LINE_CHANNEL_SECRET` | LINE Webhook 驗簽密鑰 | line-gateway |
| `LINE_NOTIFY_GROUP_ID` | 升級通知的 LINE 群組 ID | customer-service-agent |
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | Trello API 憑證 | customer-service-agent, trello-notifier, trello-board-sync |
| `DATABASE_URL` | PostgreSQL 連線字串 | 全部 agent + notifier |
| `MQTT_HOST` / `MQTT_PORT` | MQTT broker 位址（預設 mosquitto.mqtt.svc.cluster.local:1883） | line-gateway, customer-service-agent |
| `ADMIN_USER` / `ADMIN_PASS` | Admin Web UI Basic Auth | linebot-admin |
| `NAS_MOUNT_PATH` | NAS 掛載根目錄（預設 /mnt/nas/jia.homedesign） | linebot-admin |

---

## DB Schema

PostgreSQL，migration 由 `shared/db.py` 啟動時自動執行。

| 表 | 說明 |
|----|------|
| `knowledge` | Agent 語意記憶（fact + confidence） |
| `episodes` | Agent 行動紀錄 + 品質評分 |
| `working_memory` | 對話 messages（per agent_id + thread_id） |
| `trello_boards` | Trello 看板 ID ↔ 名稱，每日同步 |
| `line_users` | LINE 用戶 RBAC（role: admin/employee/vendor/customer/visitor） |
| `projects` | 工程案（case_number, Trello board, NAS path, status） |
| `line_user_projects` | 用戶與工程案的多對多關係 |

---

## 通知觸發條件摘要

| # | 時段 | 條件 | 通知對象 |
|---|------|------|---------|
| 1 | noon | 距**開始日** 1～7 天（每日） | sponsor |
| 2 | morning | 今天 = 開始日 | sponsor |
| 3 | noon | 距**結束日** 1～7 天（每日）且未完成 | sponsor + SA/Larry |
| 4 | morning | 今天 = 結束日（時間未到）且未完成 | sponsor + SA/Larry |
| 5 | evening | 今天 = 結束日（時間已過）且未完成 | sponsor + SA/Larry |
| 6 | evening | 結束日已過期（weekday）且未完成 | sponsor + SA/Larry |
| 7 | noon | Checklist 停滯 ≥ 3 天 | SA / Larry |
| 8 | noon | Checklist 全部完成 | sponsor |
| 9 | morning | 每日固定摘要 | SA / Larry |

詳見 `trello-line-design.md`。

---

## Trello 卡片標記格式

只有含 `[@(姓名),日期區間]` 標記的項目才觸發通知：

```
[@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚
[@(Larry)@(SA),-20260530] 防水層施工驗收
[@(sa),20260505-20260512]
```

- 多人負責：每人前加 `@`，如 `[@(Larry)@(SA),...]`
- 結束時間（選用）：`HHMM`，如 `:1800`
- 標籤文字可空白（工項名稱自動帶入 card 名稱）
- 支援位置：checklist 項目、card description 第一行

---

## 部署（k8s）

此 repo 只含應用程式碼，k8s manifests 在 **per-user repo**（如 `jg-jiahd`）管理。

```bash
# 推送映像（GitHub Actions 自動觸發）
git push origin main
# → GHCR: ghcr.io/ferry133/linebot:latest

# 查看 linebot namespace 狀態（jg-jiahd）
KUBECONFIG=/path/to/kubeconfig-sa kubectl -n linebot get pods

# 手動觸發 CronJob（例如 board sync）
KUBECONFIG=... kubectl -n linebot create job --from=cronjob/trello-board-sync trello-board-sync-manual
```

LINE Developer Console：Webhook URL 設為 `https://<domain>/webhook`，啟用 webhook。

---

## 本機測試

```bash
pip3 install requests flask anthropic psycopg2-binary "paho-mqtt>=2.0"

# 定時通知（不需要 MQTT/DB）
TRELLO_API_KEY=... TRELLO_TOKEN=... LINE_CHANNEL_ACCESS_TOKEN=... \
  python3 trello_line_notifier.py morning

# 發送測試訊息
TRELLO_API_KEY=... TRELLO_TOKEN=... LINE_CHANNEL_ACCESS_TOKEN=... \
  python3 trello_line_notifier.py test
```
