# project-nas-provisioning Specification

## Purpose
TBD - created by archiving change project-entity-management. Update Purpose after archive.
## Requirements
### Requirement: NAS mount in pod
linebot pod SHALL 透過 HelmRelease `persistence.type: nfs` 直接掛載 NAS export，mount point 為 `/mnt/nas/jia.homedesign`，對應 NFS export `${NAS_SERVER}:/volume2/jia.homedesign`。不使用 `sc-nas` StorageClass PVC（該 provisioner 會建 sub-directory，不適合掛現有目錄結構）。

#### Scenario: Pod starts with NFS
- **WHEN** linebot pod 啟動
- **THEN** `/mnt/nas/jia.homedesign/00. 執行中案場/` 路徑可存取
- **THEN** admin_server 可在該路徑下建立子資料夾

### Requirement: Template folder
NAS 上 SHALL 存在 template 資料夾 `/mnt/nas/jia.homedesign/_template_new_project/`，由 user 手動維護，內含標準子資料夾結構與初始檔案。

#### Scenario: Template exists at provisioning
- **WHEN** 建立新專案且 template 路徑存在
- **THEN** 系統 copytree template 至目標路徑（含所有子資料夾與初始檔案）

#### Scenario: Template missing
- **WHEN** 建立新專案但 template 路徑不存在
- **THEN** 系統記錄 WARNING log，跳過 NAS provisioning 步驟
- **THEN** project record 仍正常建立，nas_path 留 null
- **THEN** API response 含 `"nas_warning": "template not found"` 欄位

### Requirement: Auto-provision NAS folder on project creation
系統 SHALL 在 POST `/api/projects` 成功後，自動在 `00. 執行中案場/` 下建立專案資料夾，並以 `shutil.copytree` 複製 template 結構。

#### Scenario: Folder naming
- **WHEN** 建立名稱為 `{name}` 的專案，案號為 `{case_number}`
- **THEN** 資料夾名稱 = Admin UI 輸入的 `folder_name` 欄位（user 自填，系統不強制格式）
- **THEN** 完整路徑 = `/mnt/nas/jia.homedesign/00. 執行中案場/{folder_name}`

#### Scenario: Folder name conflict
- **WHEN** 目標資料夾已存在
- **THEN** 系統不覆蓋，回傳 409 錯誤
- **THEN** project record 不建立（整個操作 rollback）

#### Scenario: Write path back to DB
- **WHEN** copytree 成功
- **THEN** `projects.nas_path` 更新為完整資料夾路徑

### Requirement: Shared NAS folder support
系統 SHALL 允許多個 `projects` 記錄具有相同 `nas_path` 值。`projects.nas_path` 不為 unique key，使用者可在匯入既有專案時選擇任何已存在的資料夾，無論該資料夾是否已被其他 project 引用。

#### Scenario: Import shared folder
- **WHEN** 使用者在「匯入既有專案」選擇一個已被其他 project 引用的 NAS 資料夾
- **THEN** 系統允許建立新 project，`nas_path` 設為相同路徑
- **THEN** 兩個 project 各自擁有獨立的 `case_number`、`trello_board_id` 與 `status`

### Requirement: NAS folder move respects reference count
PUT `/api/projects/<id>` 切換 status 至 `archived` 時，系統 SHALL 先查詢仍有多少其他 project（`status != 'archived'` 且 `project_id != 本筆`）引用相同 `nas_path`。若 > 0，SHALL **不搬移**實體資料夾，僅更新 DB，並在回應加入 `nas_warning: "folder still in use"`。若 = 0，SHALL 照常將資料夾從 `00. 執行中案場/` 搬到 `archived/`。

還原（`archived → active`）時對稱：若實體資料夾仍在 `00. 執行中案場/`（因其他 project 還在用而未搬），SHALL 跳過搬移；若在 `archived/`，SHALL 搬回。

#### Scenario: Archive while folder still shared
- **WHEN** project A 與 project B 都引用 `/mnt/nas/.../00. 執行中案場/王公館`，admin 將 B 改為 archived
- **THEN** 實體資料夾保持在 `00. 執行中案場/王公館`
- **THEN** B 的 DB status=archived，response 含 `nas_warning`
- **THEN** A 仍可正常查詢、推播、RBAC

#### Scenario: Archive last active reference
- **WHEN** A 已 archived 的狀況下，admin 再將 B 改為 archived
- **THEN** 實體資料夾搬到 `archived/王公館`
- **THEN** B 的 `nas_path` 更新為新位置

#### Scenario: Restore while folder still in active location
- **WHEN** 某 project 從 archived 還原，但實體資料夾因有其他 active 引用而仍在 `00. 執行中案場/`
- **THEN** 系統跳過搬移，僅更新 DB status=active 與 `nas_path` 指向 active 路徑

