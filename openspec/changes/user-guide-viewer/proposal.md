## Why

我們有了三份使用手冊（`docs/{employee,vendor,admin}-guide.md`），但實際使用者（員工、廠商、管理員）多半不是 IT，不會去 GitHub 或讀 .md 原始檔。他們唯一天天用的入口就是 LINE。需要一個「在 LINE 裡一鍵打開、而且自動只給我看我這個角色該看的那一份」的檢視方式。

關鍵觀察：**身分其實已經知道**。每一則 webhook 事件都帶 LINE `user_id`，系統本來就會查 `line_users.role`（查詢過濾、完成按鈕授權都靠它）。問題只在於——一個獨立網頁本身不帶 LINE 身分（這正是 LIFF 存在的唯一理由）。所以不需要 LIFF；只要**把 Rich Menu 的點擊導回 bot**，由本來就知道角色的 bot 來決定給哪一份手冊即可。

## What Changes

- 新增 LINE **Rich Menu**，含一顆「📖 使用說明」按鈕，設為預設 rich menu（所有好友可見）。
- 使用者點按 →（postback / 固定訊息）進 bot → bot 查 `line_users.role` → 依角色回覆**該角色手冊的連結**。**五種角色（員工／廠商／管理員／客戶／訪客）各有對應手冊**；查無記錄者視為訪客。
- linebot-admin 新增一個**免帳密**的檢視路由，把 `docs/<role>-guide.md` 即時轉成手機友善（RWD）HTML。連結帶 **短效簽章 token**（HMAC，含 role + 到期）→ 只有 bot 發出的連結有效、會過期，外洩連結無法長期讀取，且管理員手冊不會被任意人看到。
- 手冊內容**單一來源**＝已 commit 的 `docs/*.md`；改手冊＝改一個檔，網頁同步更新。

## Capabilities

### New Capabilities
- `user-guide-viewer`: 透過 LINE Rich Menu 進入、由 bot 依登入者角色派發對應使用手冊；手冊以簽章連結開啟的手機網頁呈現，內容來源為 repo 內的 `docs/*.md`。

### Modified Capabilities
<!-- 無：沿用既有 line_users 角色查詢與 Reply API，不改其需求層級行為。 -->

## Impact

- **程式碼**
  - `gateway/line_gateway.py`：建立 / 設定預設 Rich Menu 的一次性腳本或啟動流程；webhook 處理「使用說明」入口事件（postback 或固定訊息）。
  - `agents/customer_service.py`：依 `kind`／關鍵字分派到 guide handler，查角色、產生簽章連結、Reply API 回覆（免推播額度）。
  - `agents/admin_server.py`：新增 `GET /guide`（驗 token → 渲染對應 `docs/*.md` → RWD HTML），免 Basic Auth。
- **設定 / 祕密**：新增 `GUIDE_SIGNING_SECRET`（簽章用）；Rich Menu 圖片資產。
- **相依**：image 增加一個 markdown→HTML 套件（如 `markdown`）。
- **資料**：唯讀 `line_users.role`、唯讀 `docs/*.md`；無 schema 變更。
- **部署**：push linebot → CI → bump jg-base image pins → 設定 default rich menu（一次性）。
- **非目標**：不導入 LIFF / LINE Login channel；不改既有通知與查詢行為；不做手冊的線上編輯（仍以改 repo 檔為準）。
