## Purpose
管理員 Web UI：管理 LINE 用戶、角色、專案指派與顯示資料。
## Requirements
### Requirement: User list view
管理介面 SHALL 顯示所有 `line_users` 記錄，包含 display_name、LINE ID（前8碼）、role、projects 數量、建立時間。SHALL 支援依 role 篩選。

#### Scenario: View all users
- **WHEN** admin 開啟管理介面
- **THEN** 頁面顯示所有用戶列表，依建立時間倒序排列
- **THEN** 每筆顯示：顯示名稱、大頭貼縮圖、角色 badge、可存取專案數

#### Scenario: Filter by role
- **WHEN** admin 選擇篩選 role=visitor
- **THEN** 列表只顯示 role=visitor 的用戶

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

### Requirement: Employee cannot set admin role
員工角色的管理員 SHALL NOT 可將其他用戶設為 admin；只有 admin 可指派 admin 角色。

#### Scenario: Employee tries to set admin
- **WHEN** 以 employee 身分登入的管理員嘗試將用戶設為 admin
- **THEN** admin 選項在下拉選單中不顯示或為 disabled

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

### Requirement: Import dialog shows all NAS folders
匯入既有專案 dialog 的「NAS 資料夾」下拉 SHALL 列出 `00. 執行中案場/` 下所有資料夾，不過濾已被其他 project 引用者。提示文字 SHALL 改為說明可共用。

#### Scenario: List unfiltered folders
- **WHEN** admin 點選「匯入既有專案」
- **THEN** 下拉顯示 `00. 執行中案場/` 下所有資料夾（不論是否已被引用）
- **THEN** 提示文字「同一資料夾可被多個專案共用」

### Requirement: Import dialog accepts custom case_number
匯入既有專案 dialog SHALL 提供「案號」輸入欄（選填）。留空時提交，後端 auto-gen；有填時以該值作為案號。

#### Scenario: Custom case number on import
- **WHEN** admin 在匯入 dialog 填入 case_number = `115-001-王公館A`
- **THEN** 送出 POST body 含 `case_number: "115-001-王公館A"`
- **THEN** 後端以該值建立 project

#### Scenario: Empty case number on import
- **WHEN** admin 在匯入 dialog 留空 case_number 欄位
- **THEN** 送出 POST body 未含 case_number 或為空字串
- **THEN** 後端 auto-gen `{民國年}年第N案`

### Requirement: Edit dialog allows any NAS folder
編輯既有專案 dialog 的「NAS 路徑」下拉 SHALL 列出 `00. 執行中案場/` 下所有資料夾（與匯入 dialog 同源），admin 可選擇任意資料夾，包含已被其他 project 引用者。後端 PUT `/api/projects/<id>` SHALL NOT 對 `nas_path` 做唯一性檢查。

#### Scenario: Reassign edit to shared folder
- **WHEN** admin 編輯 project B 並將 NAS 下拉改為已被 project A 引用的資料夾
- **THEN** 儲存成功，B 的 `nas_path` 更新為該共用路徑
- **THEN** A 不受影響

### Requirement: Archive warning when folder shared
當 admin 將 project 切到 archived，且該專案的 NAS 資料夾仍被其他 active project 引用時，UI SHALL 顯示提示訊息說明資料夾未實際搬移。

#### Scenario: Archive shared project shows warning
- **WHEN** archive 成功但 response 含 `nas_warning: "folder still in use"`
- **THEN** UI alert：「資料夾仍有其他進行中專案使用，本次不搬移實體資料夾」

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

