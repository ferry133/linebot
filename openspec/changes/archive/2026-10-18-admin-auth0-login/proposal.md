## Why

Admin UI（`https://linebot-admin.jiahd.cc/`）目前用固定帳密 Basic Auth（`ADMIN_USER`/`ADMIN_PASS`）：一組共用密碼、無法辨識是誰登入、密碼外洩只能輪替。改用 Auth0 登入，並限定只有 `jiahdadm@gmail.com`、`ferry133@gmail.com` 能進入。

同時修掉一個既有缺陷：`PUT /api/users/<id>` 的「只有 admin 能指派 admin」檢查用 Basic Auth 帳號比對 `line_users.display_name`，帳號是 `admin`、永遠比不到 → 該檢查實際上擋下所有人。

## What Changes

- **BREAKING** 移除 Basic Auth 與 `ADMIN_USER`/`ADMIN_PASS`；改為 Flask 內建 Auth0 OIDC（Authorization Code flow，linebot 專用 Auth0 application，與 jg-base 的 oauth2-proxy／factory tenant 無關）。
- 新增 `/login`、`/callback`、`/logout` 路由；登入後以 Flask signed session cookie（Secure、HttpOnly、SameSite=Lax）維持。
- 登入者 email 必須 `email_verified=true` 且在 allowlist（`ADMIN_ALLOWED_EMAILS`）內；allowlist 為空或未設定 → 無人可登入（fail-closed）。
- 未登入：HTML 頁面導向 `/login`；`/api/*` 回 401 JSON。`/health` 維持免登入。
- 「指派 admin 角色」的權限判斷改用登入 email：allowlist 內的登入者即具 admin 權限。
- 新增依賴 `authlib`；新增環境變數 `AUTH0_DOMAIN`、`AUTH0_CLIENT_ID`、`AUTH0_CLIENT_SECRET`、`ADMIN_SESSION_SECRET`、`ADMIN_ALLOWED_EMAILS`。

## Capabilities

### New Capabilities
- `admin-auth`: Admin UI 的身分驗證（Auth0 OIDC 登入／登出、email allowlist、session、未登入行為）。

### Modified Capabilities
- `user-management-ui`: 「Employee cannot set admin role」改為以 Auth0 登入身分判斷 admin 權限。

## Impact

- 程式：`agents/admin_server.py`（auth decorator、新路由、`update_user` 權限檢查、前端登出連結與 401 處理）。
- 依賴：`Dockerfile` 與 `CLAUDE.md` 的 pip 清單加 `authlib`。
- 部署（jg-base，需另開 issue）：`linebot/app/secret.yaml` 新增 4 個 `${VAR}` 佔位（真值放 jg-jiahd `cluster-secrets.sops.yaml`）；`admin.yaml` 以字面值設 `ADMIN_ALLOWED_EMAILS`、移除 `ADMIN_USER`/`ADMIN_PASS` env。
- 外部：Auth0 新建 Regular Web Application，Allowed Callback `https://linebot-admin.jiahd.cc/callback`、Allowed Logout `https://linebot-admin.jiahd.cc/`（需人工於 Auth0 Dashboard 操作）。
