## 1. DB migration

- [ ] 1.1 新增 `migrations/008_project_photo_folder.sql`：`ALTER TABLE projects ADD COLUMN owner_name TEXT`、`ADD COLUMN site_name TEXT`、`ADD COLUMN project_type TEXT`
- [ ] 1.2 加 CHECK constraint：`ALTER TABLE projects ADD CONSTRAINT projects_type_chk CHECK (project_type IS NULL OR project_type IN ('設計', '結構基礎', '室內裝修', '軟裝'))`
- [ ] 1.3 本機 / dev db 跑 migration 驗證（無 error、既有 row 不受影響）

## 2. admin_server.py 後端

- [ ] 2.1 修 `POST /api/projects`：接受新 input `owner_name` / `site_name` / `project_type`；若三者皆有則自動 compose `name = {o}-{s}-{t}`，否則沿用 body 帶來的 `name`
- [ ] 2.2 修 `PUT /api/projects/<id>`：接受三個欄位的更新；當更新後三欄位皆非 null 才 re-compose `name`
- [ ] 2.3 修 `GET /api/projects` 與 `GET /api/projects/<id>`：response 多回 `owner_name` / `site_name` / `project_type` 與 derived `photo_folder`
- [ ] 2.4 `photo_folder` derive helper（純 function：`(owner, site) -> "{owner}-{site}" or None`）
- [ ] 2.5 invalid `project_type` 在 POST/PUT 回 400 含明確錯誤訊息（API-layer 額外把關，與 DB CHECK 雙保險）
- [ ] 2.6 unit tests for POST / PUT / GET 行為（三個 scenarios 對應 spec）

## 3. admin UI（dialog `pdlg`）

- [ ] 3.1 新增 / 編輯 dialog 加三個輸入：「業主姓名」TEXT、「案場名稱」TEXT、「專案型態」 select(設計/結構基礎/室內裝修/軟裝)
- [ ] 3.2 三欄位皆有值時，dialog 顯示「名稱會是：{owner}-{site}-{type}」preview
- [ ] 3.3 submit 改成送 `owner_name` / `site_name` / `project_type`，不再送 `name`（或留 fallback：當三欄位為空，沿用舊 `name` input）
- [ ] 3.4 編輯既有 row：若三欄位皆 null，dialog 頂端顯示「請補充」橫幅；可只填部分欄位送出
- [ ] 3.5 list table 多加一欄「相片資料夾」永久顯示（在 `Trello 看板` 與 `NAS 資料夾` 之間，顯示 derived `photo_folder` 值），便於 admin 一眼核對 synology-photo-tagger 會用到的 folder slug

## 4. 驗證 & 部署

- [ ] 4.1 本機跑完整 round-trip：建立新 project（三欄位） → GET 確認 `photo_folder` 正確 → 編輯改 type → `name` 重組
- [ ] 4.2 既有 row 回歸測試：未碰三欄位的 row 行為與本 change 套用前 100% 一致
- [ ] 4.3 build docker image、bump digest in jg-base、Flux reconcile（流程同 [[jg-jiahd deploy 文件]]）
- [ ] 4.4 production 至少把 1 個案編輯成結構化欄位（例：曾宇晟-大宅天景-結構基礎），確認 `GET /api/projects` 內含 `photo_folder = "曾宇晟-大宅天景"`
- [ ] 4.5 **資料整理**：把既有 `曾宇晟-大宅天景-室內裝修工程` 那筆編輯為 `室內裝修`（拿掉「工程」尾綴），統一進 enum；其他若有類似變體一併處理

## 5. 收尾

- [ ] 5.1 archive 本 change
- [ ] 5.2 通知 synology-photo-tagger 那邊可以開 `tagger-auto-move` change 開工
