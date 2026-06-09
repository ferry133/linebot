# 計劃：Trello 自動監控 + LINE 通知系統

## Context

Larry 希望建立自動化流程：由 Claude 定時檢查 Trello 看板狀態，依據觸發條件自動發 LINE 通知給客戶、工班師傅、SA/Larry 本人及內部員工，取代人工逐一追蹤。

---

## 重要前提說明：LINE 帳號限制

**個人 LINE 無法透過 API 發送訊息**（LINE 官方技術限制）。
建議改用 **LINE Official Account 輕用量方案（免費）**：
- 月費：NT$0
- 每月免費則數：200 則
- 以意念情境的案量（5～10 個進行中），每月約 60～120 則，**免費額度足夠**

---

## 系統架構

```
GitHub Actions → GHCR (ghcr.io/ferry133/linebot)
         ↓
Kubernetes CronJob（jg-base repo，timeZone: Asia/Taipei）
  ├─ morning  09:00 Mon–Sat
  ├─ noon     12:00 Sun–Sat
  └─ evening  18:00 Mon–Sat
         ↓
  trello_line_notifier.py [morning|noon|evening]
  （jiahomedesign1 工作區所有看板）
         ↓
  比對九項通知條件
         ↓
  呼叫 LINE Messaging API
         ↓
  通知對應的人
```

---

## Checklist 項目 / Card Description 格式

格式：
```
[@(姓名),yyyymmdd-yyyymmdd(:HHMM)] 項目名稱
```

日期區間格式（三種皆可）：

| 格式 | 說明 | 範例 |
|------|------|------|
| `yyyymmdd-` | 只有開始日 | `20260501-` |
| `-yyyymmdd(:HHMM)` | 只有結束日（可加時間） | `-20260530:1800` |
| `yyyymmdd-yyyymmdd(:HHMM)` | 開始 + 結束（可加時間） | `20260501-20260530:1800` |

**多位 sponsor** 可並排，同時通知多人：
```
[@(姓名1)@(姓名2)@(姓名3),日期區間]
```

完整範例（checklist）：
```
□ [@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚      ← 通知曾宇晟
□ 防水層施工                                             ← 略過（無標記）
□ [@(Larry)@(SA),-20260530] 貼磁磚                     ← 同時通知 Larry 和 SA
```

**Card description 也支援相同格式**，在描述開頭加上即可：
```
[@(曾宇晟)@(Larry),20260601-20260630]
這是一張說明卡片...
```

- `@(name)`：通知對象，對應 DB `line_users.alias_name`，可多人；**名字不區分大小寫**（`larry`、`Larry`、`LARRY` 皆可）
- 日期區間：用於判斷所有時間條件
- **沒有 `[@(...)]` 格式的項目或描述，系統完全略過，不會觸發任何通知**

---

## 核心前提：所有觸發條件的共同 Precondition

> **只有含有 `[@(姓名),日期區間]` 標記的項目，才會觸發任何通知邏輯。**

這條規則適用於以下所有情境：

- **Card description**：只看第一行，必須符合 `[@...]` 格式才處理，否則整張卡略過
- **Checklist 項目**：逐項掃描，沒有 `[@...]` 的項目直接跳過
- **停滯偵測**：該 checklist 裡**至少要有一個** `[@...]` 標記項目，才會啟動停滯偵測；沒有標記的 checklist 即使超過 3 天未動也不觸發
- **全部完成偵測**：同上，該 checklist 至少有一個 `[@...]` 標記項目，才會偵測是否全部勾選完成

**常見誤解提醒：**
- 只要卡片有 checklist，就會收到停滯通知 → **❌ 錯誤**，一定要有 `[@...]` 才觸發
- 把工項名稱寫成普通文字（不加 `[@...]`），就不會被追蹤 → **✅ 正確**

---

## 觸發條件與通知對象

> 第 1～8 項皆以「含有 `[@...]` 標記的項目」為前提。第 9 項（每日摘要）固定發送，但內容只包含有標記的工項。

| # | 檢查時間 | 條件 | 通知對象 | 訊息內容 |
|---|---------|------|---------|---------|
| 1 | Sun~Sat 12:00 | 今天距離**開始日**剩 1～7 天（每日） | sponsor | 「[工項名稱] X 天後開始，請準備」 |
| 2 | Mon~Sat 09:00 | 今天 = 開始日 | sponsor | 「[工項名稱] 今日開始，請確認」 |
| 3 | Sun~Sat 12:00 | 今天距離**結束日**剩 1～7 天（每日）且**未完成** | sponsor + SA/Larry | 「[工項名稱] X 天後到期」 |
| 4 | Mon~Sat 09:00 | 今天 = 結束日（時間未到）且**未完成** | sponsor + SA/Larry | 「[工項名稱] 今日（HH:MM）到期，請確認」 |
| 5 | Mon~Sat 18:00 | 今天 = 結束日（時間已過，需有 `:HHMM`）且**未完成** | sponsor + SA/Larry | 「[工項名稱] 今日 HH:MM 已逾期，請確認」 |
| 6 | Mon~Fri 18:00 | 結束日已過期且**未完成** | sponsor + SA/Larry | 「[工項名稱] 已逾期 X 天，請確認」 |
| 7 | Mon~Sat 12:00 | Checklist 停滯超過 3 天（該 checklist 需有 `[@...]` 標記） | SA / Larry | 「[卡片名稱] 已停滯 X 天，請追蹤」 |
| 8 | Mon~Sat 12:00 | Checklist 所有項目全部勾選（該 checklist 需有 `[@...]` 標記） | sponsor | 「[卡片名稱] 所有工項已全部完成 ✓」 |
| 9 | Mon~Sat 09:00 | 每日固定摘要（無條件發送） | SA / Larry | 有標記工項的總覽；若無任何標記工項則顯示「今日無進行中工項」 |

---

## 實作步驟

### 步驟一：申請 LINE Official Account
- 網址：https://tw.linebiz.com/
- 申請免費輕用量方案
- 取得 Channel Access Token 和 Channel Secret

### 步驟二：建立姓名 → LINE ID 對應表

聯絡人統一儲存於 PostgreSQL `line_users` 資料表（linebot DB）：

| 欄位 | 說明 |
|------|------|
| `line_id` | LINE User ID（`U...`） |
| `alias_name` | 短識別名，對應 Trello 標記（如 `larry`、`sa`、`yan`），不區分大小寫 |
| `role` | `admin` / `employee` / `vendor` / `customer` / `visitor` |

通知腳本透過 `alias_name` 查詢 LINE ID：
```sql
SELECT alias_name, line_id FROM line_users WHERE alias_name = ANY(%s)
```

新增聯絡人只需在 DB 設定 `alias_name`，不需修改程式。

### 步驟三：建立通知腳本
- 檔案：`trello_line_notifier.py`
- 功能：
  1. 呼叫 Trello API 讀取所有看板與卡片
  2. 解析 checklist 項目和 card description 中的 `[@(name),date]` 格式
  3. 依 mode（morning / noon / evening）比對對應的觸發條件
  4. 從 DB `line_users`（`alias_name`）查詢 LINE ID
  5. 每位收件人**只發一則訊息**，彙整當次所有通知，以 board 為單位分組顯示

**訊息格式範例：**
```
意念情境您好，早上專案提醒：

曾宇晟｜室內裝修工程
＝＝＝＝＝＝＝＝＝＝＝＝

【🔄 未執行/1.施工許可申請】
「請屋主繳交施工保證金！」3 天後到期

【🔄 未執行/01. 委任工程約】
「屋主是否已繳交施工保證金？」今日 10:30 已逾期，請確認
```

> 開頭問候語依時段變化：早上 / 中午 / 下午

**每日摘要格式（morning）：**
```
📋 2026/04/25 每日工程摘要

曾宇晟｜室內裝修工程
＝＝＝＝＝＝＝＝＝＝＝＝
・🔄 未執行/1.施工許可申請（請屋主繳交施工保證金！）
・🔄 未執行/01. 委任工程約（屋主是否已繳交施工保證金？）
```

### 步驟四：設定環境變數
API 金鑰以 Kubernetes Secret（`linebot-secret`）管理，透過 `envFrom` 注入：
- `TRELLO_API_KEY` / `TRELLO_TOKEN`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `DATABASE_URL`（從 DB `line_users` 解析收件人）

### 步驟五：建立 Cron 排程
在 on-prem k8s 部署三個 CronJob（`timeZone: Asia/Taipei`），位於 jg-base repo：
- `morning`：Mon~Sat 09:00（`0 9 * * 1-6`）— 條件 #2、#4、#9 每日摘要
- `noon`：Sun~Sat 12:00（`0 12 * * *`）— 條件 #1、#3、#7、#8
- `evening`：Mon~Sat 18:00（`0 18 * * 1-6`）— 條件 #5、#6（#6 僅 Mon~Fri）

Flux GitOps 路徑：`jg-base/kubernetes/apps/extras/default/trello-notifier/`（linebot namespace）

---

## 關鍵檔案

| 檔案／位置 | 說明 |
|------|------|
| `trello_line_notifier.py` | 主通知腳本（production） |
| `shared/db.py` | PostgreSQL 連線池 |
| `gantt_generator.py` | 產生甘特圖 CSV |
| `gantt_sheets_sync.gs` | Google Apps Script 即時同步甘特圖 |
| `Dockerfile` | 容器映像建置，推送至 GHCR（`ghcr.io/ferry133/linebot`） |
| `jg-base/kubernetes/apps/extras/default/trello-notifier/` | 三個 CronJob 定義（linebot namespace，跑 linebot image） |
| `jg-base/kubernetes/apps/extras/default/linebot/app/` | linebot Secret（`linebot-secret`，含 `DATABASE_URL`） |

---

## 驗證方式

1. 先用 Larry 自己的 LINE ID 跑一次腳本，確認收到訊息
2. 在 Trello 新增一個有 `[@(Larry),今日日期-]` 的 checklist 項目，確認觸發
3. 確認每日摘要格式正確
4. 上線後觀察第一週訊息發送量，確認不超過 200 則免費額度

---

## 補充說明

**關於個人 LINE：** LINE 技術上不開放個人帳號的 API，但 LINE Official Account 免費版外觀與使用體驗幾乎相同，客戶加好友後就能收到通知。

---

**card 未完成定義（#3～#6 共用）：** 清單名稱為「未執行」或「執行中」，且 card 內至少有一個標記工項未完成。

---

> **單一來源說明**：本檔為通知系統設計的**權威來源**，與 production（`ghcr.io/ferry133/linebot` image）一致。
> 獨立的 `trello-notifier` repo 為 legacy fork，部署上已不使用，請勿在該 repo 維護此文件。

---

*最後更新：2026-06-09*
