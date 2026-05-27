# project-registry Specification

## Purpose
TBD - created by archiving change project-entity-management. Update Purpose after archive.
## Requirements
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
- `POST /api/projects` — 建立（觸發案號生成與 NAS provisioning；匯入分支允許自訂 `case_number`，與 `nas_path` 解耦）
- `PUT /api/projects/<project_id>` — 更新（name, trello_board_id, status, nas_path）
- `GET /api/projects/<project_id>` — 單筆查詢

匯入既有專案（`import_existing=true`）時，POST `/api/projects` SHALL 接受可選的 `case_number` 欄位：

- 若 body 含非空 `case_number`：以該值作為案號（受 unique 約束）
- 若 body 未提供或為空：呼叫 `_generate_case_number(year)` 自動產生
- `case_number` 不再強制等於所選 NAS 資料夾名；同一資料夾可對應多筆 project 記錄，但各自必須有不同 case_number

#### Scenario: Create project
- **WHEN** POST `/api/projects` body `{name, trello_board_id?}`
- **THEN** 回傳 201 含完整 project record（含自動生成的 case_number 與 project_id）

#### Scenario: List active projects
- **WHEN** GET `/api/projects?status=active`
- **THEN** 回傳所有 status=active 的 projects，依 case_number 排序

#### Scenario: Archive project
- **WHEN** PUT `/api/projects/<id>` body `{status: "archived"}`
- **THEN** status 更新為 archived，completed_at 設為 now()

#### Scenario: Import with custom case_number
- **WHEN** POST `/api/projects` body `{name, import_existing:true, nas_path:"...王公館", case_number:"115-001-王公館A"}`
- **THEN** project 以 `115-001-王公館A` 建立
- **THEN** `nas_path` 設為所選資料夾，不檢查資料夾是否已被其他 project 引用

#### Scenario: Import with auto case_number
- **WHEN** POST `/api/projects` body `{name, import_existing:true, nas_path:"...王公館"}` 未帶 case_number
- **THEN** 系統呼叫 `_generate_case_number(current_year)` 產生案號
- **THEN** project 建立成功，即使該 nas_path 已被其他 project 使用

### Requirement: Historical project record
系統 SHALL 允許建立歷史案 record，trello_board_id 與 nas_path 均可為 null，status 可設為 completed/archived。

#### Scenario: Register historical project
- **WHEN** POST `/api/projects` body `{name, status: "completed", started_at, completed_at}`
- **THEN** 建立 project record，trello_board_id=null, nas_path=null
- **THEN** 案號依建立當下年份生成（非 started_at 年份）

