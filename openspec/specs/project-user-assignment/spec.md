# project-user-assignment Specification

## Purpose
TBD - created by archiving change project-entity-management. Update Purpose after archive.
## Requirements
### Requirement: line_user_projects schema
系統 SHALL 維護 `line_user_projects` 關聯表，欄位：line_id（FK → line_users）、project_id（FK → projects）、relation（TEXT: customer/vendor）、created_at。PRIMARY KEY (line_id, project_id)。

#### Scenario: Schema integrity
- **WHEN** 同一 user 對同一 project 重複 assign
- **THEN** ON CONFLICT DO UPDATE 更新 relation，不產生重複記錄

### Requirement: Assign user to project
系統 SHALL 提供 API 將 LINE user 指派至專案：

- `PUT /api/projects/<project_id>/users` — body `[{line_id, relation}]`，全量替換該專案的人員清單
- `GET /api/projects/<project_id>/users` — 列出該專案所有人員（含 display_name、role）

#### Scenario: Assign customer and vendor
- **WHEN** PUT `/api/projects/<id>/users` body `[{line_id: "A", relation: "customer"}, {line_id: "B", relation: "vendor"}]`
- **THEN** 建立/更新兩筆 line_user_projects 記錄
- **THEN** 不在清單中的舊關聯被刪除（全量替換）

#### Scenario: List project users
- **WHEN** GET `/api/projects/<id>/users`
- **THEN** 回傳陣列，每筆含 line_id、display_name、picture_url、relation

### Requirement: Forward lookup（user → projects）
系統 SHALL 支援查詢特定 user 的所有專案：`GET /api/users/<line_id>/projects`。

#### Scenario: User's project list
- **WHEN** GET `/api/users/<line_id>/projects`
- **THEN** 回傳該 user 參與的所有 projects（含 case_number、name、status、relation）

### Requirement: Reverse lookup（project → users）用於通知
trello_line_notifier SHALL 透過 `board_id → project_id → line_user_projects` 查詢收件人，不再使用 board_name 字串比對。

#### Scenario: Notification recipient resolution
- **WHEN** CronJob 掃描 Trello 找到觸發條件，命中 board_id = `X`
- **THEN** 查 `projects` 取得 project_id（WHERE trello_board_id = X）
- **THEN** 查 `line_user_projects` 取得所有 line_id（WHERE project_id = 該 id）
- **THEN** 對各 line_id 推播 LINE 通知

#### Scenario: No project found for board
- **WHEN** board_id 未對應任何 project record
- **THEN** 記錄 WARNING log，跳過此 board 的通知，不拋出例外

