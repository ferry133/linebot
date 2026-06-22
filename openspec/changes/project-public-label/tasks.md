## 1. 對外標籤 helper

- [x] 1.1 新增 `public_label(...)`：`{site_name}-{project_type}`；缺欄位→`case_number`；永不含 owner_name
- [x] 1.2 `_all_project_names()` 改回 `{board_id: public_label}`（取代 projects.name）

## 2. 唯一性約束 + admin 拒絕

- [x] 2.1 新 migration `013_unique_site_type_active.sql`（partial unique，active 限定）；`shared/db.py` MIGRATIONS 追加
- [x] 2.2 上線前查核既有 active `(site_name, project_type)` 重複 → 0 筆，索引可順利建立
- [x] 2.3 `admin_server` `POST/PUT /api/projects`：active 重複 → 409 + 原因（含改名提示）；create 與 update（含改名/改工種/重新啟用）皆擋

## 3. LINE 顯示全面替換為 public_label

- [x] 3.1 `trello_line_notifier`：`run_checks` board 顯示用 label_map、確認卡 project、`_all_project_names` → public_label（build_flex 標頭因 board_name 已是 public_label 自動跟進）
- [x] 3.2 `customer_service`：`_all_active_projects` 與 `_get_user_role_and_projects` 的 project 標籤 → public_label（feeds `_get_user_auth` 的 project_map 與系統提示）
- [x] 3.3 `trello_agent`：回覆 `project_name` 用 public_label；**移除** fallback 到 Trello 看板原名（改「（未登錄專案）」）

## 4. 驗證

- [ ] 4.1 廠商查詢/拉取/每日 push：專案顯示為 `{site}-{type}`，無屋主名
- [ ] 4.2 主管每日摘要/確認卡/查詢：同樣無屋主名
- [ ] 4.3 任一路徑查無對照 → 顯示後備，**不**出現看板原名
- [ ] 4.4 admin 建立/更新重複 `(site,type)` active → 409 + 原因；不同工種/不同建案放行；completed 不擋

## 5. 部署

- [ ] 5.1 bump notifier + customer-service + admin image（`scripts/bump-linebot-image.sh`），migration 由 admin-server 啟動套用
- [ ] 5.2 部署後各角色實機驗證 4.1–4.4
