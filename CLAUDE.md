# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

「意念情境室內裝修」LINE 客服 Robot + 工程通知系統。

兩大功能：
1. **客服 Bot**（雙向）：客戶透過 LINE 詢問任意問題 → Claude API 理解並查詢 Trello → 即時回覆；無法回答時推播管理群組。
2. **定時通知**（單向）：CronJob 定時掃描 Trello，依九項觸發條件推播工程提醒給客戶與內部人員。

## Commands

```bash
# 安裝依賴
pip3 install requests flask anthropic psycopg2-binary

# 啟動客服 Bot Webhook Server
python3 linebot_server.py

# 執行定時通知（需先設定環境變數）
python3 trello_line_notifier.py [morning|noon|evening]

# 測試 LINE 發送
python3 trello_line_notifier.py test
```

## Architecture

```
客戶 LINE → LINE Platform → POST /webhook
                                  ↓
                         linebot_server.py (Flask)
                           ├─ 驗簽 (HMAC-SHA256)
                           ├─ 立即回 200（避免 LINE 10s timeout 重送）
                           ├─ threading.Thread → _process_message(user_id, text)
                           │    ├─ 對話記憶 (LRU OrderedDict，MAX_USERS=500，每人 20 則)
                           │    ├─ Claude API (claude-haiku-4-5) with tools:
                           │    │    ├─ query_trello(query_type, keyword)
                           │    │    └─ escalate_to_manager(reason, customer_question)
                           │    └─ Push API → 回覆客戶（非 Reply API）
                           │              ↓ escalate
                           │         Push → LINE_NOTIFY_GROUP_ID（管理群組）

CronJob → trello_line_notifier.py [morning|noon|evening]
                           ├─ Trello API 掃描所有工項
                           ├─ 九項觸發條件判斷
                           └─ LINE Push API → 客戶 / SA / Larry
```

同一個 Docker image，執行模式由 k8s workload 的 `command` 指定：
- **Webhook server**: `python /app/linebot_server.py`
- **CronJob**: `python /app/trello_line_notifier.py [morning|noon|evening]`

## Key Files

| 檔案 | 說明 |
|------|------|
| `linebot_server.py` | Flask Webhook + Claude agentic loop + 工具實作 |
| `trello_line_notifier.py` | 定時通知腳本（共用 Trello 查詢函式被 linebot_server import） |
| `gantt_generator.py` | 從 Trello 產生甘特圖 CSV（26 週，可匯入 Google Sheets） |
| `Dockerfile` | 容器映像建置，推至 GHCR（無 ENTRYPOINT，由 k8s command 指定） |
| `trello-line-design.md` | 觸發條件完整設計文件 |

## Environment Variables

| 變數 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API 金鑰（linebot_server 需要） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API 金鑰 |
| `LINE_CHANNEL_SECRET` | LINE Webhook 驗簽密鑰 |
| `LINE_NOTIFY_GROUP_ID` | 升級通知的 LINE 群組 ID |
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | Trello API 憑證 |

## linebot_server 設計細節

### Claude Agentic Loop
- **Model**: `claude-haiku-4-5-20251001`
- **MAX_HISTORY**: 20 則（in-memory LRU per user_id，重啟後清空）
- **MAX_USERS**: 500（LRU eviction，超過時淘汰最久未使用的 user）
- **MAX_TOOL_TURNS**: 5 輪（防止無限迴圈）
- **Webhook** 立即回 200，背景 `threading.Thread` 執行 Claude + Trello（避免超過 LINE 10s timeout 觸發重送）
- **Push API** 回覆客戶（非 Reply API；Reply token 在背景處理完成前已過期）
- **Push API** 同樣用於 escalate（推管理群組）

### Claude 工具

| 工具 | 觸發時機 | 動作 |
|------|---------|------|
| `query_trello(query_type, keyword)` | 客戶詢問進度/排程/逾期 | 掃描全部看板，回傳即時工項清單 |
| `escalate_to_manager(reason, customer_question)` | Claude 判斷無法回答 | Push 到 `LINE_NOTIFY_GROUP_ID`；未設定時 fallback 推播給 SA / Larry |

`query_type` 可為：`all` / `overdue` / `upcoming`（7 天內到期）/ `specific`（關鍵字）

### Escalation Fallback
若 `LINE_NOTIFY_GROUP_ID` 未設定，從 `line_contacts.json` 讀取 `sa`、`larry` 的 userId 逐一推播。

## Agent Memory DB

linebot agents 使用**自己獨立的 PostgreSQL**（與 k8scc 分開），用 `agent_id` 隔離各 Agent 的記憶：

| agent_id | 擁有者 |
|----------|--------|
| `customer_service` | LINE 客服 Agent |
| `trello_agent` | Trello 查詢 Agent |

**DB Schema**（見 `migrations/001_init.sql`）：
- `knowledge`：語意記憶，`fact` + `confidence` + `source_count`
- `episodes`：情節記憶，每次行動紀錄 + 品質評分
- `working_memory`：工作記憶，對話 messages 陣列

**env var 新增**：

| 變數 | 用途 |
|------|------|
| `DATABASE_URL` | linebot 專屬 PostgreSQL 連線字串 |

## k8s 部署備註

此 repo 只含應用程式碼，k8s manifests 需在 **per-user repo** 新增：
- **Deployment**：`command: ["python", "/app/linebot_server.py"]`，`port: 8080`
- **Service** + **HTTPRoute**（或 Ingress）：公開 Webhook URL
- **Secret**：至少需要 `ANTHROPIC_API_KEY`、`LINE_CHANNEL_ACCESS_TOKEN`、`LINE_CHANNEL_SECRET`、`LINE_NOTIFY_GROUP_ID`、`TRELLO_API_KEY`、`TRELLO_TOKEN`
- **LINE Developer Console**：Webhook URL 設為 `https://<domain>/webhook`，啟用 webhook

## Trello 標記格式

只有含 `[@(姓名),日期區間]` 標記的項目才觸發通知邏輯：

```
[@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚
[@(Larry)@(SA),-20260530] 防水層施工驗收
```
