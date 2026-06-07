## ADDED Requirements

### Requirement: Structured project name fields
`projects` 表 SHALL 新增 3 個 nullable 欄位以結構化儲存 project 命名構成：

- `owner_name`（TEXT, nullable）— 業主姓名（例：`曾宇晟`）
- `site_name`（TEXT, nullable）— 案場名稱（例：`大宅天景`、`龜山鉅力高宇C6`）
- `project_type`（TEXT, nullable, CHECK ∈ `{設計, 結構基礎, 室內裝修, 軟裝}`）— 專案型態

當三個欄位皆有值時：
- `name` SHALL 等於 `{owner_name}-{site_name}-{project_type}`
- 系統 SHALL 提供 derived 欄位 `photo_folder` = `{owner_name}-{site_name}`

當任一欄位為 null：
- `name` 可由 admin 自由輸入（沿用舊行為）
- `photo_folder` SHALL 為 null

#### Scenario: Create with all three fields
- **WHEN** POST `/api/projects` body `{owner_name:"曾宇晟", site_name:"大宅天景", project_type:"結構基礎"}`
- **THEN** 系統 SHALL 設定 `name = "曾宇晟-大宅天景-結構基礎"`
- **THEN** API response SHALL 含 `photo_folder = "曾宇晟-大宅天景"`

#### Scenario: Create with legacy name only
- **WHEN** POST `/api/projects` body `{name:"歷史案"}` 未帶三個結構化欄位
- **THEN** 系統 SHALL 建立 record，`name = "歷史案"`、三個結構化欄位為 null
- **THEN** API response 的 `photo_folder` SHALL 為 null

#### Scenario: Invalid project_type rejected
- **WHEN** POST `/api/projects` body `{..., project_type:"裝潢"}`（非合法 enum）
- **THEN** 系統 SHALL 回傳 400 並指出 `project_type` 必須是 `設計` / `結構基礎` / `室內裝修` / `軟裝` 之一

#### Scenario: Multi-到-1 photo_folder
- **WHEN** 同一 `owner_name + site_name` 建立 3 個 project（不同 `project_type`）
- **THEN** 三個 project 各自的 `photo_folder` 皆相同（= `{owner_name}-{site_name}`）

---

### Requirement: API exposes structured fields and derived photo_folder
`GET /api/projects` 與 `GET /api/projects/<project_id>` response 的每筆 project record SHALL 包含：

- 原本就有的欄位（`project_id`、`case_number`、`name`、`trello_board_id`、`nas_path`、`status`、...）
- 新增 `owner_name`（nullable）
- 新增 `site_name`（nullable）
- 新增 `project_type`（nullable）
- 新增 `photo_folder`（derived，nullable — `{owner_name}-{site_name}` 或 null）

response 欄位 order 不指定，但所有欄位 MUST 同時出現於 list 與 single GET。

#### Scenario: GET projects returns new fields
- **WHEN** `GET /api/projects?status=active`
- **THEN** response items SHALL 各含 `owner_name`、`site_name`、`project_type`、`photo_folder` 四個欄位
- **THEN** 對於三個結構化欄位皆有值的 row，`photo_folder` SHALL 為 `{owner_name}-{site_name}`
- **THEN** 對於缺 owner 或 site 的 row，`photo_folder` SHALL 為 null

#### Scenario: GET single project
- **WHEN** `GET /api/projects/<id>` 對於一個剛建立的 project
- **THEN** 同樣四個欄位皆出現於 response

---

### Requirement: PUT can backfill structured fields
PUT `/api/projects/<project_id>` SHALL 接受 `owner_name` / `site_name` / `project_type` 任一或全部欄位更新。當三者皆有值時，系統 SHALL 自動將 `name` 更新為 `{owner_name}-{site_name}-{project_type}`。

當僅更新部分結構化欄位時：
- 系統 SHALL 將提供的欄位寫入
- `name` 僅當「更新後三欄位皆非 null」時才自動 re-compose

#### Scenario: Backfill missing structured fields
- **WHEN** 既有 row `name="歷史案"` (三個結構化欄位皆 null)，PUT body `{owner_name:"陳", site_name:"老案", project_type:"設計"}`
- **THEN** 三個欄位寫入
- **THEN** `name` 更新為 `"陳-老案-設計"`
- **THEN** GET 該 project 後 `photo_folder = "陳-老案"`

#### Scenario: Partial update keeps existing name
- **WHEN** 既有 row 三欄位皆 null，PUT body `{owner_name:"陳"}`（只給 owner）
- **THEN** `owner_name` 寫入
- **THEN** `name` SHALL 不變
- **THEN** `photo_folder` SHALL 仍為 null
