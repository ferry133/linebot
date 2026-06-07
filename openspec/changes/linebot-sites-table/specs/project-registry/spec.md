## MODIFIED Requirements

### Requirement: Project entity schema
系統 SHALL 維護 `projects` table，欄位包含：project_id（UUID PK）、case_number（TEXT, 如 `115年第3案`）、name（TEXT, 資料夾顯示名）、trello_board_id（TEXT, nullable, FK → trello_boards）、status（TEXT: active/completed/archived）、started_at（TIMESTAMPTZ）、completed_at（TIMESTAMPTZ, nullable）、created_at、updated_at、**site_id（BIGINT, nullable, FK → sites.id）**。

site-level 屬性（`nas_path` 與 GPS 三欄）的**真實儲存位置 SHALL 是 `sites` table**，透過 `projects.site_id` 連到；projects 上仍保留 `nas_path / gps_lat / gps_lng / gps_radius_m` 四個欄位作為 1-release 過渡期的 back-compat 副本（read API 走 COALESCE(sites, projects)；下次小 change 才刪除）。

#### Scenario: Schema integrity
- **WHEN** 建立新 project 記錄未指定 status
- **THEN** status 預設為 `active`
- **THEN** project_id 為系統自動產生的 UUID

#### Scenario: site_id 在無 owner/site 時為 null
- **WHEN** 建立一個 legacy project，只給 `name`、未給 `owner_name` 或 `site_name`
- **THEN** projects.site_id SHALL 為 NULL（不強制建 sites row）

---

### Requirement: API exposes structured fields and derived photo_folder
`GET /api/projects` 與 `GET /api/projects/<project_id>` response 的每筆 project record SHALL 包含：

- 原本就有的欄位（`project_id`、`case_number`、`name`、`trello_board_id`、`status`、`notes`、`started_at`、`completed_at`、`created_at`、`updated_at`）
- 三個結構化欄位：`owner_name`（nullable）、`site_name`（nullable）、`project_type`（nullable）
- derived 欄位：`photo_folder`（nullable — `{owner_name}-{site_name}` 或 null）
- **site-level 欄位：`nas_path`、`gps_lat`、`gps_lng`、`gps_radius_m`（皆 nullable），值 SHALL 透過 `LEFT JOIN sites ON sites.id = projects.site_id` 取得；若 projects.site_id 為 null 或 sites 該欄為 null，SHALL fallback 到 projects 自身對應欄位（back-compat 期間）**

response 欄位 order 不指定，但所有欄位 MUST 同時出現於 list 與 single GET。

#### Scenario: GET projects returns new fields
- **WHEN** `GET /api/projects?status=active`
- **THEN** response items SHALL 各含 `owner_name`、`site_name`、`project_type`、`photo_folder` 四個欄位
- **THEN** 對於三個結構化欄位皆有值的 row，`photo_folder` SHALL 為 `{owner_name}-{site_name}`
- **THEN** 對於缺 owner 或 site 的 row，`photo_folder` SHALL 為 null

#### Scenario: GET single project
- **WHEN** `GET /api/projects/<id>` 對於一個剛建立的 project
- **THEN** 同樣四個欄位皆出現於 response

#### Scenario: site-level 欄位走 JOIN 取
- **WHEN** project 有 `site_id`、對應 sites row 有 GPS 與 nas_path
- **THEN** API response 的 `gps_lat / gps_lng / gps_radius_m / nas_path` SHALL 等於 sites 上的值（即使 projects 上殘留的 back-compat 副本不同）

#### Scenario: legacy row 走 projects 欄位 fallback
- **WHEN** project 的 `site_id` 為 null 但 projects 上 `nas_path` 有值
- **THEN** API response 的 `nas_path` SHALL 等於 projects 上的值

## ADDED Requirements

### Requirement: Site entity schema
系統 SHALL 維護 `sites` table，作為「同案場不同 project_type 共用」的 site-level 屬性儲存位置。

欄位：
- `id`（BIGSERIAL PK）
- `owner_name`（TEXT, NOT NULL）— 業主姓名
- `site_name`（TEXT, NOT NULL）— 案場名稱
- `gps_lat`（REAL, nullable）— WGS84 緯度
- `gps_lng`（REAL, nullable）— WGS84 經度
- `gps_radius_m`（INTEGER, nullable, DEFAULT 50）— 命中半徑（公尺）
- `nas_path`（TEXT, nullable）— NAS 案場資料夾絕對路徑
- `created_at`（TIMESTAMPTZ, NOT NULL, DEFAULT now()）
- `updated_at`（TIMESTAMPTZ, NOT NULL, DEFAULT now()）
- UNIQUE constraint：`(owner_name, site_name)`
- CHECK constraint：GPS 三欄沿用既有 `projects` 上的限制（lat ∈ [-90, 90]、lng ∈ [-180, 180]、radius_m ∈ [1, 5000]；lat 與 lng 必須同時 null 或同時非 null）

#### Scenario: 唯一性
- **WHEN** 嘗試 INSERT 第二筆 `(owner_name="曾宇晟", site_name="大宅天景")`
- **THEN** 系統 SHALL 因為 UNIQUE constraint 違反而拒絕

#### Scenario: GPS 兩欄必須成對
- **WHEN** INSERT 帶 `gps_lat=24.8` 但不帶 `gps_lng`
- **THEN** CHECK constraint SHALL 拒絕

---

### Requirement: Site-level fields propagate to all project_type variants
當 admin 更新一個 project 的 site-level 欄位（gps_lat / gps_lng / gps_radius_m / nas_path），系統 SHALL 把這些值寫到該 project 對應的 sites row（而非 projects row），讓**同 site_id 的所有其他 projects 在下次 GET 時立刻看到新值**。

- `POST /api/projects` 帶 site-level 欄位 + (owner_name, site_name) 同時非 null → upsert 進 sites（INSERT ON CONFLICT DO UPDATE）、project.site_id 寫好
- `PUT /api/projects/<id>` 帶 site-level 欄位 → UPDATE sites row（其他共用 site_id 的 projects 自動受惠）
- `PUT /api/projects/<id>` 改 owner_name 或 site_name 導致 (owner, site) 組合改變 → upsert 新 sites row、改寫 project.site_id 指向新 site；舊 sites row **不刪**（可能還被別的 project 引用）

過渡期內：`POST` 與 `PUT` SHALL **同時**把 site-level 欄位寫一份到 projects（back-compat 副本）；下個 release 才停。

#### Scenario: PUT 更新 GPS 自動 propagate 到 sibling
- **WHEN** `劉正群-龜山鉅力高宇C6` 有 `-設計` 與 `-室內裝修` 兩個 project，共用同 site_id；admin PUT `-室內裝修` 的 GPS 為 (25.05, 121.36)
- **THEN** GET `-設計` 那筆 project SHALL 回傳同樣的 (25.05, 121.36)，無需 admin 再對該筆操作

#### Scenario: POST 新案場建 site
- **WHEN** POST `/api/projects` body `{owner_name:"張三", site_name:"和平東路", project_type:"設計", gps_lat:25.0, gps_lng:121.5}`、sites 中尚無對應 row
- **THEN** 系統 SHALL 建一個新的 sites row、把 site_id link 上、site 的 GPS 設為 (25.0, 121.5)

#### Scenario: POST 既有案場第二個 project_type
- **WHEN** POST 一個與既有 sites row (張三, 和平東路) 同的 owner+site、但 project_type 為 `室內裝修`、不帶 GPS
- **THEN** 系統 SHALL **不**建新 sites row，直接 reuse 既有的（同個 site_id）；新 project 透過 JOIN 也看得到既有 GPS

#### Scenario: PUT 改 owner_name 切換到不同 site
- **WHEN** 既有 project 屬於 site (張三, 和平東路)；PUT body `{owner_name: "李四"}`、sites 中已有 (李四, 和平東路) row
- **THEN** 系統 SHALL 把 project.site_id 改指向 (李四, 和平東路) 的 sites row
- **THEN** 原 sites row (張三, 和平東路) **不刪除**（保留供其他可能 reference 的 project）

---

### Requirement: Migration 010 data backfill
Migration `010_sites.sql` SHALL 在 schema 改完後完成 idempotent 的 data backfill：

1. 對 projects 所有 `(owner_name, site_name)` 兩欄皆非 null 的組合，`INSERT INTO sites ... ON CONFLICT DO NOTHING`
2. 對每個 sites row，從同組 projects 抓 GPS 與 nas_path 寫入：優先取「gps_lat 非 null」者；同條件再取 `updated_at` 最新；使用 `COALESCE(sites.col, ranked.col)` 確保已有值不被覆蓋
3. 把 `projects.site_id` 設為對應 sites.id，只更新 `projects.site_id IS NULL` 的 row

Migration 跑第二次 SHALL 不破壞任何資料、不重複建 sites row、不覆蓋 admin 手動改過的 sites 值。

#### Scenario: 首次 migration 把 7 個 projects 連到 6 個 sites
- **WHEN** migration 跑在含 7 個 projects（3 個 `曾宇晟-大宅天景` × 不同 type、2 個 `劉正群-龜山鉅力高宇C6`、2 個 `陳永華-創世紀M3`）的 DB
- **THEN** sites 表 SHALL 有 3 個 row（依不同 owner-site 組合）
- **THEN** 7 個 projects 的 site_id 都 SHALL 非 null 且正確 link

#### Scenario: 第二次 migration 不重複建
- **WHEN** 已跑過 migration、又重跑一次
- **THEN** sites 表 row 數量不變、admin 手動改過的 sites 值不被覆蓋

#### Scenario: GPS 從「有」的 row 流到 sites
- **WHEN** 既有 projects 兩個共用 (劉正群, 龜山鉅力高宇C6)、`-室內裝修` 有 GPS、`-設計` 無
- **THEN** migration 後 sites row 的 GPS SHALL 等於 `-室內裝修` 的 GPS（優先取有 GPS 的 row）

---

### Requirement: Admin UI hint for site-level fields
`templates/admin.html`（或 admin_server.py 內 HTML 字串）的 GPS 區塊與 NAS 路徑區塊 SHALL 在欄位上方加 hint 文字，例：「⚙️ 此欄位屬於案場（業主-案場）。同案場不同 project type 共用同一組值」。

hint 文字 SHALL 出現在新增 dialog 與編輯 dialog 兩種情境；其餘 UI 元件、layout、JS 互動邏輯**不變**。

#### Scenario: 編輯 dialog 顯示 hint
- **WHEN** admin 點某 project 的「編輯」按鈕、開啟 pdlg
- **THEN** GPS 與 NAS 兩個區塊上方 SHALL 顯示 hint 文字、提示這是案場共用欄位

#### Scenario: 新增 dialog 顯示 hint
- **WHEN** admin 點「+ 新增專案」、開啟空 pdlg
- **THEN** 同樣的 hint 文字 SHALL 出現於 GPS / NAS 區塊
