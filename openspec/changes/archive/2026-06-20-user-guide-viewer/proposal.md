## Why

我們有了五份角色使用手冊（`docs/{employee,vendor,admin,customer,visitor}-guide.md`），但實際使用者多半不是 IT，不會去 GitHub 或讀 .md 原始檔。他們唯一天天用的入口就是 LINE。需要一個「在 LINE 對話裡一鍵打開、依角色顯示、可逐主題瀏覽」的線上說明。

關鍵觀察：**身分在對話端本就已知**——每則訊息／postback 都帶 `user_id`，系統本來就會查 `line_users.role`。獨立網頁才需要 LIFF／token／官網登入這類身分機制；既然把入口留在對話內，就完全不需要那些。因此採「Rich Menu 點擊 → 回 bot（已知角色）→ 直接在對話內呈現線上說明」。

## What Changes

- 新增 LINE **Rich Menu**「📖 使用說明」按鈕（`postback o=guide`），設為預設。
- bot 收到後依 `line_users.role` 在**對話內**呈現該角色的**線上說明**：
  - **主題選單**：列出該手冊各 `##` 主題為按鈕。
  - **單一主題**：顯示該段內容，附**目前位置 (i/N)** 與 上一/下一/目錄/完整手冊 導覽。
  - **完整手冊**：整份文字（標出「▶ 你在這」），隨時可回目錄。
- 全程走 **Reply API**（免推播額度），訊息可帶 Flex 按鈕（gateway outbox 擴充支援 messages 陣列）。
- 手冊內容**單一來源**＝`docs/*.md`，以 `##` 切段、markdown 輕量轉為 LINE 可讀文字；改手冊＝改一個檔。

## Capabilities

### New Capabilities
- `user-guide-viewer`: 透過 LINE Rich Menu 進入、由 bot 依登入者角色在**對話內**呈現線上說明（主題選單 / 單一主題＋位置導覽 / 完整手冊），內容來源為 `docs/<role>-guide.md`。

### Modified Capabilities
<!-- 無：沿用既有 line_users 角色查詢與 Reply API；gateway outbox 僅擴充為可帶 messages 陣列，不改其需求層級行為。 -->

## Impact

- **程式碼**
  - `gateway/line_gateway.py`：outbox 支援 `messages` 陣列（Flex），reply/push 共用；建立預設 Rich Menu 的一次性腳本。
  - `agents/customer_service.py`：`op=="guide"` → `_handle_guide` 依角色與 postback（主題/完整）回覆對應訊息；關鍵字「使用說明」備援。
  - `shared/guide.py`（新）：載入 `docs/<role>-guide.md`、`##` 切段、markdown→LINE 文字、組主題選單/單一主題/完整手冊訊息。
- **資產**：Rich Menu 圖片由設定腳本以 PIL 自動產生（或自備）。
- **資料**：唯讀 `line_users.role`、唯讀 `docs/*.md`；無 schema 變更。
- **部署**：push linebot → CI → bump jg-base image pins → 設定 default rich menu（一次性）。
- **非目標**：不開網頁、不用 LIFF／token／官網登入；不改既有通知與查詢；不做手冊線上編輯。
