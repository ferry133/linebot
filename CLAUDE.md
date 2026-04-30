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
pip3 install requests flask anthropic

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
                           ├─ 對話記憶 (in-memory per user_id，保留 20 則)
                           ├─ Claude API (claude-haiku-4-5) with tools:
                           │    ├─ query_trello(query_type, keyword)
                           │    └─ escalate_to_manager(reason, customer_question)
                           └─ Reply API → 回覆客戶
                                  ↓ escalate
                           Push → LINE_NOTIFY_GROUP_ID（管理群組）

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
| `trello_line_notifier.py` | 定時通知腳本（共用 Trello 查詢函式） |
| `Dockerfile` | 容器映像建置，推至 GHCR |
| `trello-line-design.md` | 觸發條件完整設計文件 |

## Environment Variables

| 變數 | 用途 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API 金鑰（linebot_server 需要） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API 金鑰 |
| `LINE_CHANNEL_SECRET` | LINE Webhook 驗簽密鑰 |
| `LINE_NOTIFY_GROUP_ID` | 升級通知的 LINE 群組 ID |
| `TRELLO_API_KEY` / `TRELLO_TOKEN` | Trello API 憑證 |

## Trello 標記格式

只有含 `[@(姓名),日期區間]` 標記的項目才觸發通知邏輯：

```
[@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚
[@(Larry)@(SA),-20260530] 防水層施工驗收
```
