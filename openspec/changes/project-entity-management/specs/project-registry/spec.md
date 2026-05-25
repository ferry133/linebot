## ADDED Requirements

### Requirement: Project entity schema
系統 SHALL 維護 `projects` table，欄位包含：project_id（UUID PK）、case_number（TEXT, 如 `115年第3案`）、name（TEXT, 資料夾顯示名）、trello_board_id（TEXT, nullable, FK → trello_boards）、nas_path（TEXT, nullable）、status（TEXT: active/completed/archived）、started_at（TIMESTAMPTZ）、completed_at（TIMESTAMPTZ, nullable）、created_at、updated_at。

#### Scenario: Schema integrity
- **WHEN** 建立新 project 記錄未指定 status
- **THEN** status 預設為 `active`
- **THEN** project_id 為系統自動產生的 UUID

### Requirement: 案號自動生成
系統 SHALL 在建立新專案時自動產生案號，格式為 `{民國年}年第{N}案`，N 為當年既有案號的下一個流水號（含所有 status）。

#### Scenario: First case of the year
- **WHEN** 建立第一個 2026 年（民國115年）的專案
- **THEN** case_number = `115年第1案`

#### Scenario: Subsequent cases
- **WHEN** 當年已有 3 個案號時建立新專案
- **THEN** case_number = `{year}年第4案`

#### Scenario: No gap filling
- **WHEN** 某年已有第1、第2、第4案（第3案被刪除）
- **THEN** 新案號為 `{year}年第5案`（取 MAX+1，不填補空缺）

### Requirement: Project CRUD
系統 SHALL 提供 REST API 對 projects 做 CRUD：

- `GET /api/projects` — 列表（含 filter: status, year）
- `POST /api/projects` — 建立（觸發案號生成與 NAS provisioning）
- `PUT /api/projects/<project_id>` — 更新（name, trello_board_id, status, nas_path）
- `GET /api/projects/<project_id>` — 單筆查詢

#### Scenario: Create project
- **WHEN** POST `/api/projects` body `{name, trello_board_id?}`
- **THEN** 回傳 201 含完整 project record（含自動生成的 case_number 與 project_id）

#### Scenario: List active projects
- **WHEN** GET `/api/projects?status=active`
- **THEN** 回傳所有 status=active 的 projects，依 case_number 排序

#### Scenario: Archive project
- **WHEN** PUT `/api/projects/<id>` body `{status: "archived"}`
- **THEN** status 更新為 archived，completed_at 設為 now()

### Requirement: Historical project record
系統 SHALL 允許建立歷史案 record，trello_board_id 與 nas_path 均可為 null，status 可設為 completed/archived。

#### Scenario: Register historical project
- **WHEN** POST `/api/projects` body `{name, status: "completed", started_at, completed_at}`
- **THEN** 建立 project record，trello_board_id=null, nas_path=null
- **THEN** 案號依建立當下年份生成（非 started_at 年份）
