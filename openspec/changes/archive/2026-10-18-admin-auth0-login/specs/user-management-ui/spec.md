## MODIFIED Requirements

### Requirement: Employee cannot set admin role
只有具 admin 權限的登入者 SHALL 可將用戶設為 admin。登入者身分以 Auth0 session 的 email 判定：email 在 `ADMIN_ALLOWED_EMAILS` 內者即具 admin 權限；無有效 session 者 SHALL NOT 指派 admin。

#### Scenario: Employee tries to set admin
- **WHEN** 無有效 admin session 的請求嘗試將用戶設為 admin
- **THEN** 系統回 403（未登入則 401），不更新 role

#### Scenario: Allowlisted admin sets admin
- **WHEN** 以 allowlist 內 email 登入的管理員將用戶設為 admin
- **THEN** DB 更新 role=admin
