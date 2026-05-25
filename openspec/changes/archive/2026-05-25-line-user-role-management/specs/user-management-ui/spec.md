## ADDED Requirements

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
admin 或 employee 角色的管理員 SHALL 可透過介面將任意用戶的 role 升級，並指派可存取的 Trello 專案。

#### Scenario: Upgrade visitor to customer
- **WHEN** admin 點選某 visitor 用戶的「編輯」
- **THEN** 彈出對話框，顯示目前角色與可選角色（vendor/customer，不含 admin）
- **WHEN** admin 選擇 customer 並勾選對應看板後儲存
- **THEN** DB 更新 role=customer、projects=[...]
- **THEN** 下一則該用戶的訊息即套用新權限（無需重啟）

#### Scenario: Assign projects to vendor
- **WHEN** admin 將 role 設為 vendor 並指派專案
- **THEN** 看板清單從 `trello_boards` DB table 動態拉取，以勾選方式選擇

### Requirement: Employee cannot set admin role
員工角色的管理員 SHALL NOT 可將其他用戶設為 admin；只有 admin 可指派 admin 角色。

#### Scenario: Employee tries to set admin
- **WHEN** 以 employee 身分登入的管理員嘗試將用戶設為 admin
- **THEN** admin 選項在下拉選單中不顯示或為 disabled
