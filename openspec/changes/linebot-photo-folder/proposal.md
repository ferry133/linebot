## Why

下游系統 `synology-photo-tagger` 要做「相片自動 move 到 `/photo/officephoto/<project X>/YYYYMM/`」，需要拿到一個**短、唯一、跨 `型態` 共用**的 folder slug。
目前 `linebot.projects.name` 是合併好的字串（例：`曾宇晟-大宅天景-結構基礎`），缺乏結構化欄位、無法可靠拆解（`室內裝修` vs `室內裝修工程` 等變體會壞）。
本 change 把「業主名 / 案場名 / 專案型態」拆成獨立欄位，並對外多回一個 derived `photo_folder`（= `業主-案場`），讓 `synology-photo-tagger` 直接消費。

## What Changes

- **`projects` 表新增 3 個欄位**：`owner_name`、`site_name`、`project_type`（前兩者 TEXT、最後一個 TEXT + CHECK enum `設計 / 結構基礎 / 室內裝修 / 軟裝`）
- 3 個欄位**皆 nullable**（向下相容；既有 row 不強制 backfill）
- **Admin UI 新增 / 編輯 dialog 改成輸入三個獨立欄位**（業主、案場、型態 drop-down），系統自動 compose `name = {業主}-{案場}-{型態}`
- **`GET /api/projects` 與 `GET /api/projects/<id>` response 多回**：
  - 三個原始欄位 `owner_name` / `site_name` / `project_type`
  - 一個 derived 欄位 `photo_folder` = `{業主}-{案場}`（若任一缺則為 null）
- `POST /api/projects` 接受 `owner_name` / `site_name` / `project_type` 為新 input；若提供則用 derived `name`，否則沿用舊行為（直接傳 `name`）
- 既有 row（3 欄位為 null）的編輯 dialog 顯示「請補充」提示，但不強制
- **沒有 BREAKING**：所有現有 API、UI 路徑與既有 row 仍可運作

## Capabilities

### New Capabilities
（無）

### Modified Capabilities
- `project-registry`: `projects` 表 schema 新增 3 欄；API 回傳新欄位 + derived `photo_folder`
- `user-management-ui`: 新增 / 編輯 project dialog 改為三欄輸入；自動 compose `name`

## Impact

- **程式**：[agents/admin_server.py](agents/admin_server.py)（POST/PUT/GET `/api/projects`、UI dialog `pdlg`）
- **DB migration**：新增 `migrations/008_project_photo_folder.sql`，3 個 nullable 欄位 + CHECK constraint
- **下游**：`synology-photo-tagger` 後續會以本 change 暴露的 `photo_folder` 作為 `/photo/officephoto/<project X>/` 的 folder name
- **非影響**：RBAC、客服查詢、Trello 通知、NAS 資料夾 provisioning 流程
