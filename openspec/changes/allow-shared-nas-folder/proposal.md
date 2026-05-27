## Why

實務上同一個 NAS 案場資料夾可能對應多個 Trello 看板 / 多個 project 記錄（例如同一案分階段、多包工程）。目前「匯入既有專案」會把已被任一 project 引用的 NAS 資料夾過濾掉，且強制 `case_number = 資料夾名`，導致無法為共用資料夾建立第二個 project。

## What Changes

- 解除「匯入既有專案」對 NAS 資料夾的綁定唯一性限制：列表顯示所有 `00. 執行中案場/` 下的資料夾，不再排除已被引用者。
- 匯入流程下 `case_number` 與 `NAS 資料夾名` **解耦**：使用者可在 dialog 額外輸入案號；若留空則 auto-gen（沿用 `_generate_case_number`）。
- 後端 `POST /api/projects` 匯入分支允許多筆 `projects.nas_path` 指向相同實體路徑。
- **封存連動調整**：archived/restore 搬動 NAS 資料夾時，若仍有其他 active project 引用同一 `nas_path`，**不搬移實體資料夾**，僅更新 DB 狀態；最後一個引用切到 archived 時才搬。

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `project-nas-provisioning`: NAS 資料夾與 project 改為多對一；archive/restore 的搬移行為依「是否最後一個 active 引用」決定
- `project-registry`: `case_number` 與 `nas_path` 解耦，匯入不再以資料夾名作案號；`nas_path` 允許多筆重複
- `user-management-ui`: 匯入 dialog 改顯示全部資料夾，並新增可選案號欄位

## Impact

- 程式：[agents/admin_server.py](agents/admin_server.py)（`/api/nas/folders` 過濾、POST `/api/projects` 匯入分支、PUT 狀態切換時的 NAS 搬移邏輯、`pdlg` 匯入 UI）
- DB：無 schema 變更（`projects.nas_path` 本就無 UNIQUE 約束）
- 不影響：RBAC、客服查詢、通知推播（皆以 `project_id` / `trello_board_id` 為單位，與 NAS 路徑共用無關）
