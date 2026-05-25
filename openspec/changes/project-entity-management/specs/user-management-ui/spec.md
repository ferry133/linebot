## ADDED Requirements

### Requirement: Project management page
Admin UI SHALL 新增「Projects」分頁，提供專案的建立、檢視、編輯與封存。

#### Scenario: View project list
- **WHEN** admin 切換至 Projects 分頁
- **THEN** 顯示所有 projects，每筆含：案號、名稱、Trello 看板（名稱）、NAS 路徑、狀態、人員數
- **THEN** 可依 status 篩選（active/completed/archived）

#### Scenario: Create new project
- **WHEN** admin 點選「新增專案」
- **THEN** 彈出表單，欄位：名稱、NAS 資料夾名稱（預填案號建議值）、Trello 看板（下拉，從 /api/boards 拉）、備註
- **WHEN** admin 提交
- **THEN** 系統建立 project record、自動生成案號、在 NAS 建立資料夾
- **THEN** 列表即時更新

#### Scenario: Edit project
- **WHEN** admin 點選專案的「編輯」
- **THEN** 可修改 name、trello_board_id、status
- **THEN** nas_path 唯讀顯示（不可透過 UI 修改）

#### Scenario: Archive project
- **WHEN** admin 將 status 改為 archived
- **THEN** 該專案從 active 列表消失，仍可在 all 篩選中查看

### Requirement: alias_name 設定
Admin UI SHALL 在 user 編輯 dialog 中新增 `alias_name` 欄位（text input），供 Admin 設定或清除。欄位旁 SHALL 顯示提示：「用於 Trello 標記與系統識別，設定後請避免變更」。

#### Scenario: Set alias_name
- **WHEN** admin 在編輯 dialog 填入 alias_name = "wang" 並儲存
- **THEN** 若唯一性通過，DB 更新成功，列表顯示 alias badge
- **THEN** 若衝突，顯示錯誤訊息「此簡稱已被使用」，不關閉 dialog

#### Scenario: Display alias in user list
- **WHEN** user 有 alias_name
- **THEN** 用戶列表該筆顯示 alias badge（如 `larry`）於 display_name 旁

## MODIFIED Requirements

### Requirement: Role upgrade
admin 或 employee 角色的管理員 SHALL 可透過介面將任意用戶的 role 升級，並指派可存取的**專案**（改為從 `/api/projects` 拉清單，取代原本的 Trello board name 勾選）。

#### Scenario: Upgrade visitor to customer
- **WHEN** admin 點選某 visitor 用戶的「編輯」
- **THEN** 彈出對話框，顯示目前角色與可選角色
- **WHEN** admin 選擇 customer 並勾選對應**專案**後儲存
- **THEN** DB 更新 role=customer
- **THEN** `line_user_projects` 建立對應記錄（relation=customer）
- **THEN** 下一則該用戶的訊息即套用新權限

#### Scenario: Assign projects to vendor
- **WHEN** admin 將 role 設為 vendor 並指派專案
- **THEN** 專案清單從 `/api/projects?status=active` 動態拉取，以勾選方式選擇
- **THEN** 每個勾選的專案在 `line_user_projects` 建立 relation=vendor 記錄
