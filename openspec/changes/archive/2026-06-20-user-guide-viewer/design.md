## Context

五份手冊已存在於 `docs/{employee,vendor,admin,customer,visitor}-guide.md`（已 commit）。使用者多為非 IT，日常入口只有 LINE。

身分判定現況：每則 webhook 事件帶 `user_id`；`line_users.role` 由 DB 查得（`_user_identity`）。gateway 已能解析 `postback` event 成 `kind="postback"` 投遞 customer-service；`_process_postback` 依 `op` 分派。回覆走 Reply API（`reply_token`，免推播額度）。

關鍵限制：獨立網頁不自帶 LINE 身分（這是 LIFF／token／官網登入存在的理由）。本設計把入口留在**對話內**，bot 端本就知道身分，因此完全不需要那些機制。

## Goals / Non-Goals

**Goals:**
- LINE 對話內一鍵打開、依角色顯示、可逐主題瀏覽的線上說明。
- 不開網頁、不引入任何網頁身分機制（LIFF／token／官網登入）。
- 內容單一來源＝`docs/*.md`，改檔即更新。
- 不消耗推播額度（走 Reply API）。

**Non-Goals:**
- 不開網頁版手冊、不用 LIFF／簽章 token／官網登入。
- 不做手冊線上編輯（仍改 repo 檔）。
- 不改既有通知、查詢、完成按鈕等行為。

## Decisions

**D1：對話內呈現，不開網頁。**
Rich Menu「📖 使用說明」用 `action: postback`、`data="o=guide"`。gateway 既有 postback 流程送進 customer-service；`_process_postback` 對 `op=="guide"` → `_handle_guide`。bot 端已知 `user_id` → 查 `role`，直接在對話內回覆，無需網頁自證身分。
- 替代（網頁版＋LIFF／token／官網登入）：否決——為唯讀手冊增加身分機制與安全面（曾因簽章 token fail-open 觸發 HIGH 安全發現），且使用者本就在對話內。

**D2：三種視圖，以 postback 切換。**
- **主題選單**（無 `s`）：Flex bubble，列出該手冊各 `##` 主題為按鈕（`o=guide&s=<i>`）＋「📄 完整手冊」（`o=guide&s=all`）。
- **單一主題**（`s=<i>`）：Flex bubble，header 顯示**位置 `(i+1/N)`** 與主題名，body 為該段文字，footer 導覽：上一（`s=i-1`，首節省略）/下一（`s=i+1`，末節省略）/☰目錄（`o=guide`）/📄全部（`o=guide&s=all&c=i`）。
- **完整手冊**（`s=all[&c=<i>]`）：整份文字分則送出，目前所在段標「▶（你在這）」，末附「☰ 回主題目錄」。

**D3：gateway outbox 擴充支援 messages 陣列。**
`_on_outbox` 既有只送單則文字；改為可帶 `messages`（LINE message dict 陣列，含 Flex），reply/push 共用，單次上限 5 則；無 `messages` 時回退 `content` 文字。既有純文字回覆不受影響。

**D4：內容單一來源 `docs/<role>-guide.md`，markdown 輕量轉 LINE 文字。**
`shared/guide.py` 以 `## ` 切段（跳過 H1／前言）；轉換：`**粗體**`/`` `code` `` 去標記、`[text](url)`→`text（url）`、表格列→「・a ｜ b」、`---`→分隔線、`>` 引言→「💬 …」。改手冊只需改該 md 檔並重建 image。
- **`docs/` 需在 image 內**（既有 Dockerfile 已 `COPY docs/`，customer-service 讀取）。

**D5：角色↔手冊對應（五種角色皆有手冊）。**
admin/employee/vendor/customer/visitor 各對應一份 `docs/<role>-guide.md`；查無 `line_users` 記錄者視為 `visitor`。

**D6：入口與備援。**
單一預設 Rich Menu（`postback o=guide`）給所有好友；另以關鍵字「使用說明／操作說明／help…」文字訊息走同一 `_handle_guide`（rich menu 圖片缺失時的備援）。

**D7：交付與部署。**
純程式變更 + 一次性 rich menu 設定。部署：push linebot → CI → bump jg-base 全部 image pins → 執行 `setup_richmenu.py`。無新增 env、無 schema 變更。

## Risks / Trade-offs

- **長手冊**：完整手冊分則送（≤5 則、每則 ≤5000 字）；極長則截斷——目前各手冊遠低於上限。
- **單一主題 Flex 內文過長**：一般主題段落足夠；極長段落逼近 bubble 上限時需精簡內容。
- **markdown→文字有損**（表格、樣式）：可接受，定位為「可讀」而非還原排版；完整排版仍以 repo md 為準。
- **Reply API 需 reply_token**：postback／訊息事件皆有；主動推播才需額度，本功能不主動推。
