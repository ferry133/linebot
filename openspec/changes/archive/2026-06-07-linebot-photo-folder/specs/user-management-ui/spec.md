## ADDED Requirements

### Requirement: Project create/edit dialog uses three structured inputs
新增 / 編輯 project 的 dialog SHALL 用三個獨立輸入元件取代單一 `name` 欄位：

- 「業主姓名」TEXT input（對應 `owner_name`）
- 「案場名稱」TEXT input（對應 `site_name`）
- 「專案型態」drop-down select（對應 `project_type`，選項 `設計` / `結構基礎` / `室內裝修` / `軟裝`）

UI SHALL 在三個欄位皆有值時，**即時 preview** 自動 compose 出的 `name`（例：`曾宇晟-大宅天景-結構基礎`），讓使用者送出前確認最終 tag 名稱。

#### Scenario: Live preview of name
- **WHEN** 使用者在 dialog 三個欄位輸入 `曾宇晟`、`大宅天景`、選 `結構基礎`
- **THEN** dialog SHALL 顯示 preview「名稱會是：曾宇晟-大宅天景-結構基礎」

#### Scenario: Submit with all three fields
- **WHEN** 使用者按確認送出
- **THEN** dialog SHALL 把 `owner_name` / `site_name` / `project_type` 三個欄位送 POST `/api/projects`
- **THEN** 不需要前端另送 `name`，由後端自動 compose

---

### Requirement: Legacy projects can edit structured fields
編輯既有 project 時，若該 row 三個結構化欄位皆 null，dialog SHALL 顯示「請補充業主 / 案場 / 型態」提示橫幅，但**不強制必填**送出。
若該 row 已有部分欄位，dialog SHALL 預填那些欄位。

#### Scenario: Legacy row prompt
- **WHEN** 編輯 row 三個結構化欄位皆 null
- **THEN** dialog SHALL 在頂端顯示提示橫幅（不擋送出按鈕）
- **THEN** 使用者可只更新部分欄位、或全部跳過保留原 `name`

#### Scenario: Partial backfill
- **WHEN** 編輯時填入 `owner_name` 與 `site_name`、`project_type` 留空，按送出
- **THEN** 兩個欄位寫入
- **THEN** `name` 不變（因為三欄位未齊全）
- **THEN** dialog 關閉、列表 refresh 仍顯示原 `name`
