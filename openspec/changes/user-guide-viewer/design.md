## Context

三份手冊已存在於 `docs/{employee,vendor,admin}-guide.md`（已 commit）。使用者多為非 IT，日常入口只有 LINE。

身分判定現況：每則 webhook 事件帶 `user_id`；`line_users.role` 由 DB 查得（`_user_identity` / `_get_user_role_and_projects`），既有查詢過濾與完成按鈕授權都依此。gateway 已能解析 `postback` event 成 `kind="postback"` 投遞 customer-service；`_process_postback` 依 `op` 分派。回覆走 Reply API（`reply_token`，免推播額度）。

linebot-admin（`agents/admin_server.py`，Flask）已有對外 ingress 與 HTML 服務能力，目前所有路由 `@require_auth`（Basic Auth）。

關鍵限制：**獨立網頁不自帶 LINE 身分**——這是 LIFF 的唯一用途。本設計不引入 LIFF，改用「Rich Menu 點擊 → 回 bot（已知角色）→ bot 發角色專屬連結」繞過此限制。

## Goals / Non-Goals

**Goals:**
- LINE 內一鍵打開、自動只給使用者其角色該看的手冊。
- 不新增 LINE Login channel / LIFF app。
- 手冊內容單一來源＝`docs/*.md`，改檔即更新。
- 管理員手冊不被任意人讀取（gating 不靠登入頁）。
- 不消耗推播額度（回覆走 Reply API）。

**Non-Goals:**
- 不導入 LIFF / LINE Login。
- 不做手冊線上編輯（仍改 repo 檔）。
- 不改既有通知、查詢、完成按鈕等行為。
- 不做多語系。

## Decisions

**D1：不用 LIFF，改用 bot 中介身分。**
Rich Menu 的「📖 使用說明」按鈕用 `action: postback`、`data="o=guide"`。gateway 既有 postback 流程把它送進 customer-service；`_process_postback` 新增 `op=="guide"` → `_handle_guide`。bot 端本就知道 `user_id` → 查 `role`，不需網頁自證身分。
- 替代（LIFF 自證）：否決——需建 LINE Login channel + LIFF app + 驗 ID token，為了一個唯讀手冊不划算。

**D2：派發方式＝回一條「簽章連結」，不直接貼手冊全文。**
markdown 的表格/分段在 LINE 純文字/Flex 內可讀性差且有長度限制。改回一則含按鈕的訊息，連到手機網頁。回覆用 `reply_token`（Reply API，免額度）。
- 替代（Flex/文字直接回全文）：否決——排版差、易超長；列為降級備案。

**D3：連結帶短效 HMAC 簽章 token，網頁免登入但受控。**
bot 產生 `token = base64url(role|exp|sig)`，`sig = HMAC_SHA256(GUIDE_SIGNING_SECRET, f"{role}|{exp}")`。連結形如 `https://<admin-host>/guide?t=<token>`。
admin 端 `GET /guide`（**不**走 `@require_auth`）驗 `sig` 與 `exp` 未過期 → 取 `role` → 渲染 `docs/<role>-guide.md`。
- TTL 取短（預設 24h）：外洩連結僅短期有效；管理員手冊不會被任意人長期讀取。
- 後台網址本身非憑證（後台仍 Basic Auth），故即便短期外洩風險可接受。
- 替代（純公開 `/guide/<role>`）：否決——管理員手冊網址可被猜/外洩、世界可讀。

**D4：渲染伺服器端、單一來源＝`docs/*.md`。**
`/guide` 以 markdown 套件把 `docs/<role>-guide.md` 轉 HTML，套一段極簡 RWD CSS（手機可讀、字級適中）。改手冊只需改該 md 檔並重建 image。
- **`docs/` 需 COPY 進 image**（現 Dockerfile 未含）→ 加一行 `COPY docs/ ./docs/`。

**D5：角色↔手冊對應（五種角色皆有手冊）。**
共 5 份 `docs/*-guide.md`，每種角色都派發其對應手冊，無「無手冊」分支；查無 `line_users` 記錄者視為 `visitor`。

| role | 連結手冊 |
|------|------|
| admin | `admin-guide` |
| employee | `employee-guide` |
| vendor | `vendor-guide` |
| customer | `customer-guide` |
| visitor（含查無記錄） | `visitor-guide` |

**D6：單一預設 Rich Menu（給所有好友）。**
建立一個 default rich menu（含使用說明按鈕），用 `POST /v2/bot/user/all/richmenu/{id}` 設為預設。角色判斷一律在點擊後由 bot 處理，非適用角色得到友善訊息，而非看到不屬於他的手冊。
- 替代（per-role rich menu 綁定）：否決——需逐人 link richmenu，維運複雜，效益低。
- Rich Menu 需一張圖片資產（PNG）；建立為一次性 API 腳本（`gateway/` 下），記錄於 tasks。

**D7：交付與部署。**
純程式變更 + 一次性 rich menu 設定。新增 env `GUIDE_SIGNING_SECRET`（bot 與 admin 兩邊都需，值相同）。部署：push linebot → CI → bump jg-base image pins（9 處）→ 設定 default rich menu。

## Risks / Trade-offs

- **簽章連結 TTL 內外洩** → 他人可於 TTL 內讀該角色手冊。緩解：短 TTL；手冊非機密、後台另有 Basic Auth。
- **`GUIDE_SIGNING_SECRET` 兩邊不一致** → 連結一律驗不過、開不了。緩解：同一 Secret 來源，部署檢查。
- **docs 未進 image** → `/guide` 404/讀不到。緩解：Dockerfile 加 `COPY docs/`，並於 pod 驗證檔案存在。
- **Rich Menu 圖片/設定為一次性手動** → 文件化步驟；圖片缺失只影響入口外觀，不影響 bot 邏輯（仍可由關鍵字「使用說明」觸發作為備援）。
- **Reply API 需 reply_token** → postback 事件有帶；正常。若改為主動推播會吃額度，故維持回覆式。
