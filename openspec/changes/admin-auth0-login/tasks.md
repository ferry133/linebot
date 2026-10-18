## 1. 依賴與設定

- [x] 1.1 Dockerfile 與 CLAUDE.md pip 清單加入釘版本的 `authlib`
- [x] 1.2 `admin_server.py` 讀取 `AUTH0_DOMAIN`/`AUTH0_CLIENT_ID`/`AUTH0_CLIENT_SECRET`/`ADMIN_SESSION_SECRET`/`ADMIN_ALLOWED_EMAILS`；`ADMIN_SESSION_SECRET` 缺漏時啟動失敗；移除 `ADMIN_USER`/`ADMIN_PASS`
- [x] 1.3 設定 session cookie（Secure、HttpOnly、SameSite=Lax、7 天）與 `ProxyFix(x_proto=1, x_host=1)`

## 2. 登入流程

- [x] 2.1 註冊 authlib OAuth client（`server_metadata_url=https://<AUTH0_DOMAIN>/.well-known/openid-configuration`，scope `openid profile email`）
- [x] 2.2 `/login`（保存站內 `next`）、`/callback`（驗 `email_verified` + allowlist，否則 403）、`/logout`（清 session + Auth0 `/v2/logout`）
- [x] 2.3 改寫 `require_auth`：每次比對 session email 與 allowlist；`/api/*` 回 401 JSON、頁面 302 `/login`；`/health` 不套用

## 3. 權限與前端

- [x] 3.1 `update_user` 的 admin 指派檢查改用 session email ∈ allowlist，移除 `display_name` 比對
- [x] 3.2 前端：fetch 收到 401 導向 `/login`；頁首顯示登入 email 與「登出」連結

## 4. 測試

- [x] 4.1 `tests/smoke_admin_auth.py`：以 Flask test_client 驗未登入 `/`→302、`/api/users`→401、Basic Auth→401、`/health`→200；注入 session 後 allowlist 內→200、移出 allowlist→401；callback 邏輯以 mock userinfo 驗非名單／未驗證→403、空 allowlist→403

## 5. 部署（跨 repo）

- [x] 5.1 ferry133 於 Auth0 建 linebot 專用 Regular Web App，Allowed Callback `https://linebot-admin.jiahd.cc/callback`、Allowed Logout `https://linebot-admin.jiahd.cc/`
- [x] 5.2 在 jg-base 開 issue（ferry133/jg-base#189；`ADMIN_USER/ADMIN_PASS` 移除須在新 image 驗證後——舊 image 缺值會 fallback `admin/changeme`）：`linebot/app/secret.yaml` 加 4 個 `${VAR}` 佔位（AUTH0_* ×3、ADMIN_SESSION_SECRET）、`admin.yaml` 以字面值設 `ADMIN_ALLOWED_EMAILS`（非祕密，不經 postBuild）並移除 `ADMIN_USER/ADMIN_PASS` env（署名 `linebot-e6 [609b4b]`）
- [x] 5.3 jg-jiahd `cluster-secrets.sops.yaml` 寫入 4 個值（jg-jiahd `06c4d36`）
- [x] 5.4 PR merge → CI → `bump-linebot-image.sh` → reconcile；實測兩個 email 可登入、其他帳號 403、未登入 API 401
- [x] 5.5 移除舊 `ADMIN_USER/ADMIN_PASS`——量到兩者從未設定（線上實為 `admin/changeme`），已於 jg-base `93f2fc1` 一併移除 env
- [x] 5.6 偽造／過期 `/callback`（state 不符、Auth0 回 error）回 400 而非 500
