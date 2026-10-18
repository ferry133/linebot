# admin-auth Specification

## Purpose
Admin UI（`linebot-admin.jiahd.cc`）的身分驗證：以 linebot 專用 Auth0 application 做 OIDC 登入，由 app 內的 email allowlist 決定誰能進入（Auth0 只證明身分）。
## Requirements
### Requirement: Auth0 OIDC login
Admin UI SHALL 以 Auth0 OIDC（Authorization Code flow）驗證管理員身分，SHALL NOT 接受固定帳密（Basic Auth）。

#### Scenario: Unauthenticated page request
- **WHEN** 未登入的使用者開啟 `/`
- **THEN** 系統以 302 導向 `/login`，再導向 Auth0 登入頁

#### Scenario: Unauthenticated API request
- **WHEN** 未登入的請求呼叫任一 `/api/*`
- **THEN** 系統回 401 JSON，且不執行該 API

#### Scenario: Basic Auth no longer accepted
- **WHEN** 請求附帶 `Authorization: Basic ...` 但無有效 session
- **THEN** 系統視為未登入

#### Scenario: Health check stays open
- **WHEN** 任何人呼叫 `/health`
- **THEN** 系統回 200，不需登入

### Requirement: Email allowlist
系統 SHALL 僅允許 `email_verified=true` 且 email（不分大小寫）列於 `ADMIN_ALLOWED_EMAILS` 的使用者登入；allowlist 為空或未設定時 SHALL 拒絕所有人。預設部署 allowlist 為 `jiahdadm@gmail.com`、`ferry133@gmail.com`。

#### Scenario: Allowed email logs in
- **WHEN** `jiahdadm@gmail.com`（已驗證）於 Auth0 登入成功並回到 `/callback`
- **THEN** 系統建立 session 並導向 `/`

#### Scenario: Non-allowlisted email rejected
- **WHEN** 其他 email 於 Auth0 登入成功並回到 `/callback`
- **THEN** 系統回 403，不建立 session

#### Scenario: Unverified email rejected
- **WHEN** allowlist 內的 email 但 `email_verified` 不為 true
- **THEN** 系統回 403，不建立 session

#### Scenario: Empty allowlist fails closed
- **WHEN** `ADMIN_ALLOWED_EMAILS` 未設定或為空
- **THEN** 任何人登入皆回 403

#### Scenario: Removed from allowlist
- **WHEN** 已登入使用者的 email 被移出 allowlist 後再發出請求
- **THEN** 該請求視為未登入

### Requirement: Session and logout
登入後 SHALL 以簽章 session cookie（Secure、HttpOnly、SameSite=Lax，效期 7 天）維持；SHALL 提供 `/logout` 清除 session 並登出 Auth0。

#### Scenario: Logout
- **WHEN** 已登入使用者點選「登出」
- **THEN** 本地 session 被清除，並導向 Auth0 logout 後回到站台

#### Scenario: Missing session secret
- **WHEN** `ADMIN_SESSION_SECRET` 未設定
- **THEN** admin server 啟動失敗並記錄原因

