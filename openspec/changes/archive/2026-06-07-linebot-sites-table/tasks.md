## 1. Migration

- [x] 1.1 新檔 `migrations/010_sites.sql`：建 sites table（含 UNIQUE + CHECK constraints）、加 projects.site_id + index
- [x] 1.2 同檔內加 idempotent data backfill SQL（design D2 三步驟：INSERT DISTINCT sites + ranked UPDATE + UPDATE projects.site_id）
- [x] 1.3 `shared/db.py` 的 `MIGRATIONS` list append `"010_sites.sql"`
- [x] 1.4 local 跑兩次 migration（mock DB / local container）確認 idempotent；row 數不變

## 2. admin_server.py — Read path

- [x] 2.1 `list_projects()` SQL 加 `LEFT JOIN sites s ON s.id = p.site_id`、SELECT 多帶 `COALESCE(s.gps_lat, p.gps_lat) AS gps_lat` 等 4 個 site-level 欄位
- [x] 2.2 `get_project(project_id)` 同樣加 JOIN + COALESCE
- [x] 2.3 確認 API response 欄位名稱與順序不變（synophoto 端不需動）

## 3. admin_server.py — Write path

- [x] 3.1 helper `_upsert_site(conn, owner_name, site_name, gps_fields, nas_path) -> site_id`：用 `INSERT ... ON CONFLICT (owner_name, site_name) DO UPDATE SET ...` 寫 sites、回 id；GPS / nas_path 用 COALESCE 不覆蓋 null
- [x] 3.2 `create_project()` 內：若 owner_name + site_name 都非 null → 呼叫 `_upsert_site`、把 site_id 寫 projects；同步寫一份 GPS/nas_path 到 projects 欄位（back-compat）
- [x] 3.3 `update_project()` 內：
  - 把 PUT body 拆 site-level 欄位 vs project-level 欄位
  - 若 PUT 改了 owner_name 或 site_name → 取新組合 upsert sites + 更新 project.site_id
  - 否則：用既有 project.site_id 對應的 sites row UPDATE site-level 欄位
  - 同步寫一份到 projects 欄位（back-compat）
- [x] 3.4 confirm transaction 包覆：一個 PUT request 的 sites + projects 兩個 UPDATE 在同一 transaction、任一失敗整批 rollback

## 4. admin UI hint

- [x] 4.1 在 dialog 的 GPS 區塊 `<label>` 後面加 `<div class="hint">⚙️ 此欄位屬於案場（業主-案場）。同案場不同 project type 共用同一組值</div>`
- [x] 4.2 在 NAS 路徑區塊（編輯模式才出現）做同樣 hint
- [x] 4.3 不動 JS、不動 layout、不動 input

## 5. 端對端驗證（in pod, post-deploy）

- [x] 5.1 deploy 後檢查 migration 跑成功：`kubectl -n linebot logs deploy/linebot-admin | grep "010_sites"`
- [x] 5.2 GET /api/projects 確認 7 筆都有 site_id（log 出來看）
- [x] 5.3 PUT `劉正群-龜山鉅力高宇C6-室內裝修` 的 GPS = (25.0553, 121.3643) → GET `-設計` 那筆，確認 GPS 同步亮起
- [x] 5.4 PUT `陳永華-創世紀M3-室內裝修` 的 GPS = (24.8027, 120.9950) → GET `-設計` 那筆同樣同步
- [x] 5.5 POST 新案場（owner_name="測試業主", site_name="測試案場", project_type="設計", GPS）→ 確認 sites + projects 都建出來
- [x] 5.6 PUT 同案場 site_name 改字 → upsert 新 sites + 改 site_id（驗證 D5 rename 行為）
- [x] 5.7 第二次跑 migration（手動 `psql -c` 重跑 010 內容）→ 確認 row 數不變、admin 改的 GPS 沒被覆寫

## 6. 部署

- [x] 6.1 commit linebot repo（migration + admin_server + admin UI）；push main → GHCR build
- [x] 6.2 jg-base linebot-admin digest bump + commit + push
- [x] 6.3 annotate gitrepository jg-base + kustomization extras-linebot（兩個都要）
- [x] 6.4 pod rollout 完成 → 5.x 驗證

## 7. 文件

- [x] 7.1 linebot `README.md` 的「資料表」段落加 sites 行；「結構化欄位」段落補一句「GPS / nas_path 規範化在 sites table、API 透過 JOIN 帶出」
- [x] 7.2 不更新 synophoto repo（無變動；下次回去做 progress-album 時不需 mention）

## 8. 收尾

- [x] 8.1 archive change → `openspec/changes/archive/YYYY-MM-DD-linebot-sites-table/`
- [x] 8.2 sync project-registry 主 spec（MODIFIED 與 ADDED 兩段都要落到 `openspec/specs/project-registry/spec.md`）
- [x] 8.3 memory `project_roadmap_decisions.md` 加一筆「linebot-sites-table archived；下一個 drop projects 上 4 個 back-compat 欄位的小 change 待開」（不立刻做）
- [x] 8.4 RESUME `progress-album` 在 synophoto repo（從 Ch2 開始 — Ch1 spike 已完成）
