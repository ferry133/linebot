## Context

`agents/admin_server.py` 是單檔 Flask app（HTML 內嵌、`/api/*` JSON），經 jg-base 的 HTTPRoute（envoy-external）對外於 `linebot-admin.jiahd.cc`，綁 `0.0.0.0:8081`。所有路由以 `@require_auth`（Basic Auth）保護。使用者明確要求 linebot 獨立接 Auth0，不沿用 jg-base 的 oauth2-proxy sidecar 與 factory tenant。

## Goals / Non-Goals

**Goals:**
- Auth0 OIDC 登入，只允許兩個 email，fail-closed。
- 不改 manifest 結構（不加 sidecar、Service/port 不變），部署只需新增 secret 鍵。
- 修正 admin 指派權限檢查。

**Non-Goals:**
- 不做多角色（employee）登入 admin UI；allowlist 內皆為 admin。
- 不改 LINE 端任何 RBAC。
- 不做 server-side session store。

## Decisions

1. **Flask 內建 OIDC（authlib）而非 oauth2-proxy sidecar**：使用者裁定 linebot 與 jg-base 脫鉤。authlib 的 Flask client 處理 state／nonce／id_token 驗證（JWKS），比手刻 code exchange 少踩 JWT 驗證的坑。
2. **授權閘門在 app 內**：Auth0 只證明身分；`ADMIN_ALLOWED_EMAILS`（逗號分隔、小寫比對）決定能否進入。另要求 `email_verified`，避免 Auth0 database connection 註冊未驗證信箱冒用。Allowlist 為空 → 全部拒絕。
3. **每次請求重驗 allowlist**：session 只存 email；`require_auth` 每次比對當前 allowlist，移除名單後既有 session 立即失效（不必等 cookie 過期）。
4. **Session**：Flask signed cookie，`ADMIN_SESSION_SECRET` 簽章；`SESSION_COOKIE_SECURE/HTTPONLY`、`SameSite=Lax`（OIDC callback 是 top-level GET 導回，Lax 可帶 cookie）；`PERMANENT_SESSION_LIFETIME=7d`。`ADMIN_SESSION_SECRET` 未設定時啟動失敗（不 fallback 到隨機值，避免多副本/重啟後無聲登出且掩蓋設定缺漏）。
5. **redirect_uri**：`ProxyFix(x_proto=1, x_host=1)` 讓 `url_for('callback', _external=True)` 在 envoy 後產生 `https://linebot-admin.jiahd.cc/callback`；Auth0 端 Allowed Callback 白名單擋下偽造 Host。
6. **未登入行為**：`/api/*` 回 `401 {"error":"unauthorized"}`（前端 fetch 收到 401 → `location='/login'`）；其他頁面 302 到 `/login?next=`（next 只接受站內相對路徑）。
7. **CSRF**：寫入 API 皆為 JSON fetch；SameSite=Lax 擋跨站 POST/PUT 帶 cookie，足夠此內部工具。
8. **admin 指派權限**：`update_user` 改以 `session['email'] ∈ allowlist` 判定（等同已登入即 admin），刪除 `display_name` 比對。

## Risks / Trade-offs

- [Auth0 未設定 callback 或 secret 未就位 → 登入 100% 失敗] → 部署前先在 Auth0 建 app、jg-jiahd 放好 secret；rollback 為回上一個 image sha。
- [image 與 secret 不同步：新 image 缺 `ADMIN_SESSION_SECRET` 啟動失敗] → 先上 secret（reconcile），再 bump image；readinessProbe 會讓舊 pod 持續服務。
- [只有兩人、無 break-glass] → 兩個信箱互為備援；必要時 `kubectl port-forward` + 回滾 image。
- [authlib 新依賴] → 釘版本於 Dockerfile。

## Migration Plan

1. Auth0 Dashboard 建 Regular Web App，設定 callback／logout URL，取得 client id/secret。
2. jg-jiahd `cluster-secrets.sops.yaml` 加 4 個祕密值；jg-base `linebot/app/secret.yaml` 加佔位，`admin.yaml` 以字面值設 `ADMIN_ALLOWED_EMAILS`（名單不是祕密，放在 manifest 裡才看得到誰能進）、移除 `ADMIN_USER/ADMIN_PASS`（jg-base issue）。
3. linebot PR merge → CI build → `bump-linebot-image.sh` → reconcile。
4. 驗證：兩個 email 可登入；其他 Google 帳號被拒；未登入 `/api/users` 回 401；`/health` 200。
5. 移除 jg-jiahd 舊 `ADMIN_USER/ADMIN_PASS` 值。

Rollback：回 bump 前的 image sha（舊 image 仍讀 `ADMIN_USER/ADMIN_PASS`，故第 5 步在驗證後才做）。

## Open Questions

- Auth0 tenant 用哪個（新 tenant 或既有 tenant 下新 app）——由 ferry133 在 Dashboard 決定，程式只吃 `AUTH0_DOMAIN`。
