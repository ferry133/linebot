## 1. 檢視頁（agents/admin_server.py）

- [ ] 1.1 新增 `GET /guide`（**不**加 `@require_auth`）：解析 query `t`、驗 HMAC 簽章與到期、取 `role`。
- [ ] 1.2 token helper：`make_guide_token(role, ttl)` / `verify_guide_token(t)`，用 `GUIDE_SIGNING_SECRET`（`HMAC_SHA256(secret, f"{role}|{exp}")`，base64url）。
- [ ] 1.3 渲染：讀 `docs/<role>-guide.md` → markdown 轉 HTML → 套極簡 RWD CSS（手機可讀、`<meta viewport>`）。驗證失敗回 401/失效頁。
- [ ] 1.4 角色白名單：五種角色 `admin/employee/vendor/customer/visitor` 皆有對應 `docs/<role>-guide.md`；未知 role 回 404。

## 2. bot 派發（agents/customer_service.py）

- [ ] 2.1 `_process_postback` 新增 `op=="guide"` → `_handle_guide(user_id, reply_token)`。
- [ ] 2.2 `_handle_guide`：查 `role`（查無記錄→visitor）→ 為五種角色之任一產生簽章連結（`make_guide_token` + `GUIDE_HOST`），以 Reply API 回覆含連結訊息。
- [ ] 2.3（備援）關鍵字「使用說明」文字訊息亦走同一 `_handle_guide`，供 rich menu 圖片缺失時使用。

## 3. Rich Menu（gateway/ 一次性腳本）

- [ ] 3.1 新增 `gateway/setup_richmenu.py`：建立 rich menu（含「📖 使用說明」區塊，`postback` `data=o=guide`）、上傳圖片、設為 `richmenu/all` 預設。
- [ ] 3.2 準備 rich menu 圖片資產（2500×843 PNG，置 `assets/`）。

## 4. 打包 / 設定

- [ ] 4.1 Dockerfile 新增 `COPY docs/ ./docs/`（檢視頁需讀 md）；pip 增加 `markdown`。
- [ ] 4.2 新增 env `GUIDE_SIGNING_SECRET`（bot 與 admin 同值）與 `GUIDE_HOST`（檢視頁網址）；記錄於 CLAUDE.md env 表與 jg-base secret。

## 5. 本機驗證

- [ ] 5.1 `make/verify_guide_token` 往返測試（有效/過期/竄改/無 token）。
- [ ] 5.2 五檔 `ast.parse`；stub 匯入 `_handle_guide`、`GET /guide` 以 Flask test_client 驗 401/200 與角色對應 md。

## 6. 部署

- [ ] 6.1 commit + push linebot；CI green。
- [ ] 6.2 bump jg-base 全部 9 image pins → Flux reconcile；設 `GUIDE_SIGNING_SECRET`/`GUIDE_HOST` secret。
- [ ] 6.3 執行 `setup_richmenu.py` 設定 default rich menu（一次性）。

## 7. 部署後驗證

- [ ] 7.1 pod 內確認 `docs/*.md` 存在、`/guide` 用有效 token 回 200 並渲染對應角色手冊、過期/竄改回 401。
- [ ] 7.2 真機：LINE 點「📖 使用說明」→ 依角色收到正確手冊連結（員工/廠商/管理員各驗一次；customer/visitor 得導引訊息）。
