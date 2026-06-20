## 1. 線上說明內容模組（shared/guide.py）

- [x] 1.1 載入 `docs/<role>-guide.md`、以 `## ` 切段（跳過 H1/前言），回傳 `[(title, body)]`。
- [x] 1.2 markdown→LINE 文字：`**粗體**`/`` `code` ``去標記、`[t](u)`→`t（u）`、表格列→「・a ｜ b」、`---`→分隔線、`>`→「💬」。
- [x] 1.3 組訊息：主題選單（Flex 按鈕 `o=guide&s=i` + 完整手冊 `o=guide&s=all`）。
- [x] 1.4 組訊息：單一主題（Flex：位置 `(i/N)`、內文、上一/下一/目錄/全部；首末節省略對應箭頭）。
- [x] 1.5 組訊息：完整手冊（文字分則 ≤5000×≤4 + 標「▶ 你在這」+ 回目錄 Flex）。
- [x] 1.6 `guide_messages(role, pb)` 入口：依 `s`/`c` 回主題選單/單一主題/完整手冊；查無內容回 []。

## 2. gateway 支援 Flex 訊息（gateway/line_gateway.py）

- [x] 2.1 `_on_outbox` 支援 `messages` 陣列（Flex 等），reply/push 共用，單次 ≤5 則；無則回退 `content` 文字。

## 3. bot 派發（agents/customer_service.py）

- [x] 3.1 `op=="guide"` → `_handle_guide(user_id, reply_token, pb)`；查角色 → `guide_messages` → 以 `messages` 經 OUTBOX 回覆。
- [x] 3.2 關鍵字「使用說明」等文字訊息走同一 `_handle_guide`（主題選單）。

## 4. Rich Menu（gateway/setup_richmenu.py）

- [x] 4.1 一次性腳本：建立含「📖 使用說明」整塊 `postback o=guide` 的 rich menu、PIL 自動產底圖（或 `--image`）、設為 `richmenu/all` 預設。

## 5. 清理（不再需要網頁/token 路線）

- [x] 5.1 移除 `shared/guide_token.py`、admin `/guide` 路由與 `markdown` 依賴、`GUIDE_HOST`/`GUIDE_SIGNING_SECRET` env；保留 Dockerfile `COPY docs/`（customer-service 讀取）。

## 6. 本機驗證

- [x] 6.1 五檔 `ast.parse`；無殘留 token/web 參照。
- [x] 6.2 `guide_messages` 五角色主題數、主題選單按鈕、單一主題位置/導覽（首末節邊界）、完整手冊「你在這」/分則/≤5 則 皆通過。

## 7. 部署

- [x] 7.1 commit + push linebot；CI green。
- [x] 7.2 bump jg-base 全部 9 image pins → Flux reconcile。
- [x] 7.3 執行 `setup_richmenu.py` 設定 default rich menu（一次性）。

## 8. 部署後驗證

- [x] 8.1 pod 內確認 `docs/*.md` 存在；以 stub broker 呼叫 `_handle_guide` 驗主題選單/主題/完整手冊訊息正確。
- [ ] 8.2 真機：LINE 點「📖 使用說明」→ 主題選單 → 點主題（看位置與上一/下一）→ 完整手冊（看「你在這」）→ 回目錄；五角色各抽驗。
