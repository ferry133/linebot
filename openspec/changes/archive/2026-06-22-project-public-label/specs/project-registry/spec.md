## ADDED Requirements

### Requirement: 建案+工種對外標籤唯一
為確保對外標籤 `{site_name}-{project_type}` 無歧義，**active** 專案的 `(site_name, project_type)` 組合 SHALL 唯一（以部分唯一索引強制：`UNIQUE(site_name, project_type) WHERE status='active'`）。`POST /api/projects` 或 `PUT /api/projects/<id>` 若會造成兩個 active 專案具相同 `(site_name, project_type)`，系統 SHALL 拒絕（HTTP 409）並回明確原因，提示管理者把 `site_name` 改成可區分（如加棟別/戶別）。completed/archived 專案不納入此唯一性檢查。

#### Scenario: 重複建案+工種被擋
- **WHEN** 已有 active 專案 site_name=「創世紀M3」、project_type=「室內裝修」，admin 再建立同 `(site_name, project_type)` 的 active 專案
- **THEN** 系統回 409 與原因（此建案+工種已存在，請改用可區分的建案名，如加棟別/戶別）
- **THEN** 不建立該專案

#### Scenario: 同建案不同工種放行
- **WHEN** 已有「大宅天景-設計」，admin 建立「大宅天景-結構基礎」
- **THEN** 放行（project_type 不同，標籤唯一）

#### Scenario: 不同建案放行
- **WHEN** admin 建立 site_name 與既有皆不同的專案
- **THEN** 放行

#### Scenario: 已結案不阻擋
- **WHEN** 既有同 `(site_name, project_type)` 專案 status=completed 或 archived
- **THEN** 不阻擋新 active 專案建立（唯一性僅作用於 active）
