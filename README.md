# jiahd-trello-notifier

意念情境室內裝修 — Trello 自動監控 + LINE 通知系統

## 架構

每日定時由 Kubernetes CronJob 執行，讀取 Trello 看板，依九項條件自動發送 LINE 通知給客戶、工班師傅、SA/Larry。

```
GitHub Actions → GHCR (ghcr.io/ferry133/trello-notifier)
         ↓
Kubernetes CronJob (jg-jiahd repo, Flux GitOps)
  ├─ morning  09:00 Mon–Sat  （今日開始、今日到期、每日摘要）
  ├─ noon     12:00 Mon–Sat  （開始/結束倒數、停滯、全完成）
  └─ evening  18:00 Mon–Sat  （今日已逾期、結束日已過期）
         ↓
trello_line_notifier.py [morning|noon|evening]
  ├─ 讀取 Trello 看板與 checklist
  ├─ 解析 [@(姓名),日期區間] 標記
  └─ 發送 LINE 通知
```

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `trello_line_notifier.py` | 主要通知腳本 |
| `Dockerfile` | 容器映像建置 |
| `trello-line-design.md` | 完整系統設計文件（觸發條件、訊息格式）|

---

## 安裝步驟

### 1. 取得 Trello API 憑證

1. 前往 https://trello.com/app-key 取得 **API Key**
2. 在同頁面點擊「Token」連結，授權後取得 **Token**
3. 確認 Trello 工作區 ID（`WORKSPACE_ID` 寫在 `trello_line_notifier.py:17`，目前為 `69e43323c25d72247983debe`）

### 2. 申請 LINE Official Account

1. 前往 https://tw.linebiz.com/ 申請免費輕用量方案（200 則/月，足夠使用）
2. 進入 LINE Developers Console → Messaging API → 取得 **Channel Access Token**
3. 通知對象需先加 LINE Official Account 為好友，才能收到推播

### 3. 取得各聯絡人的 LINE User ID

每位通知對象需先加 OA 好友，再透過 Webhook 或 LINE Developers Console 取得其 `userId`（格式為 `Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）。

### 4. 更新聯絡人 ConfigMap

編輯 jg-jiahd repo 的 `kubernetes/apps/default/trello-notifier/app/configmap.yaml`：

```yaml
data:
  line_contacts.json: |
    {
      "Larry":  "U...",
      "SA":     "U...",
      "曾宇晟": "U...",
      "張師傅": "U..."
    }
```

- 名字不區分大小寫（Trello 標記中的 `@(Larry)` / `@(larry)` 皆可對應）
- 以 `備` 開頭的欄位會被略過（可用於備份舊 ID）

### 5. 更新 Kubernetes Secret

編輯 jg-jiahd repo 的 `kubernetes/apps/default/trello-notifier/app/secret.sops.yaml`，以 SOPS 加密寫入：

```
TRELLO_API_KEY
TRELLO_TOKEN
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
```

```bash
# 解密後編輯再重新加密
sops kubernetes/apps/default/trello-notifier/app/secret.sops.yaml
```

### 6. 推送映像（自動）

Push 到 `main` branch 後，GitHub Actions 自動建置並推送至 GHCR：

```
ghcr.io/ferry133/trello-notifier:latest
```

### 7. 部署至 Kubernetes（Flux 自動同步）

Flux 每 1 小時同步一次 jg-jiahd repo，自動套用 ConfigMap、Secret、CronJob。也可手動觸發：

```bash
flux reconcile kustomization trello-notifier
```

---

## Trello 卡片標記格式

只有含 `[@(姓名),日期區間]` 標記的項目才會觸發通知，格式如下：

```
[@(曾宇晟),20260501-20260530:1800] 拆除舊有磁磚
[@(Larry)@(SA),-20260530] 防水層施工驗收
```

支援位置：checklist 項目、card description 第一行。詳見 `trello-line-design.md`。

---

## 本機測試

```bash
pip3 install requests

# 建立 line_contacts.json（參考 ConfigMap 內容）
cat > line_contacts.json << 'EOF'
{
  "Larry": "U...",
  "SA":    "U..."
}
EOF

# 發送測試訊息給 Larry
TRELLO_API_KEY=... TRELLO_TOKEN=... LINE_CHANNEL_ACCESS_TOKEN=... \
  python3 trello_line_notifier.py test

# 模擬各時段執行
TRELLO_API_KEY=... TRELLO_TOKEN=... LINE_CHANNEL_ACCESS_TOKEN=... \
  python3 trello_line_notifier.py morning
```
