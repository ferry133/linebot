## 1. Backend: API 解除過濾與案號解耦

- [x] 1.1 `GET /api/nas/folders`：保留 `?unassigned=1` 行為但不再被匯入呼叫；新增說明註解（或直接移除 unassigned 分支，視 1.4 決定）
- [x] 1.2 `POST /api/projects` 匯入分支：接受 body `case_number`（選填）；有值用之，無值改呼叫 `_generate_case_number(year)`；移除「強制 case_number = 資料夾名」邏輯
- [x] 1.3 `POST /api/projects` 匯入分支：移除「資料夾已被其他 project 引用就擋掉」的檢查（若有）
- [x] 1.4 `PUT /api/projects/<id>` archive 路徑：先查同 `nas_path` 下其他 active project 數；>0 跳過 `_archive_nas_folder`，response 加 `nas_warning: "folder still in use"`
- [x] 1.5 `PUT /api/projects/<id>` restore 路徑（archived → active）：對稱判斷實體位置；若資料夾仍在 active 區則跳過搬移
- [x] 1.6 在寫入 `nas_path` 時統一 `os.path.normpath`，確保引用計數比對正確

## 2. Frontend: 匯入 dialog 改造

- [x] 2.1 `_loadNasFolders` / 匯入流程：移除 `?unassigned=1` 查詢字串，列出全部資料夾
- [x] 2.2 匯入提示文字改為「同一資料夾可被多個專案共用」
- [x] 2.3 匯入 dialog 新增「案號」輸入欄（選填），佔位文字「留空自動生成 115年第N案」
- [x] 2.4 `saveProject` 匯入分支：把案號欄值放進 body（空字串 → 不送或送空）
- [x] 2.5 儲存後若 response 含 `nas_warning: "folder still in use"` → `alert` 顯示提示

## 3. 測試與部署

- [ ] 3.1 在 dev cluster 手動驗證：建立 project A 引用某資料夾 → 再匯入 project B 用同一資料夾 → 成功
- [ ] 3.2 手動驗證 archive B 時資料夾未搬，response 有 nas_warning
- [ ] 3.3 手動驗證再 archive A（最後一個 active 引用）時資料夾搬到 archived/
- [ ] 3.4 手動驗證還原行為符合預期
- [ ] 3.5 build image、bump admin.yaml tag、push 觸發 Flux
- [ ] 3.6 手動驗證編輯 dialog NAS 下拉列出全部資料夾，且可改指到已被其他 project 引用者
