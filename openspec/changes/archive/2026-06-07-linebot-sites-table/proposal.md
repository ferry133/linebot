## Why

同一個物理案場（業主-案場）可以有多個 project_type（設計 / 結構基礎 / 室內裝修 / 軟裝），目前 `projects` table 把這些拆成多 row。`gps_lat / gps_lng / gps_radius_m / nas_path` 是**案場層級**的屬性，但被存在 project row 上 → admin 填 GPS 要對同案場每個 project_type 各填一次。

實測：`劉正群-龜山鉅力高宇C6-室內裝修` 已填 GPS、`-設計` 那 row 還是空白；`陳永華-創世紀M3-設計` 已填、`-室內裝修` 還是空。同樣是同一棟房子。

本 change 把案場層級屬性正規化到新 `sites` table，admin UI 一次填、同案場全部 project rows 共用。

## What Changes

- **新 migration `010_sites.sql`**：
  - `sites(id BIGSERIAL PK, owner_name TEXT NOT NULL, site_name TEXT NOT NULL, gps_lat REAL, gps_lng REAL, gps_radius_m INT, nas_path TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ, UNIQUE(owner_name, site_name))`
  - 沿用 `009_project_gps.sql` 的 GPS CHECK constraint（lat / lng 範圍 + radius 範圍 + lat-lng 同時 null 或同時非 null）
  - `projects` 加 `site_id BIGINT REFERENCES sites(id)` nullable
- **Data migration（同一個 migration 檔案內、idempotent）**：
  - 對 `projects` 中所有 `owner_name + site_name` 兩欄都非 null 的組合 INSERT/ON CONFLICT DO NOTHING 進 sites
  - 對每個 sites row，從該組 projects 拿 `(nas_path, gps_lat, gps_lng, gps_radius_m)` 寫入：優先取「有 GPS」的、衝突取 `updated_at` 最新者
  - 把 `projects.site_id` 設成對應 sites.id
- **`shared/db.py`** 的 MIGRATIONS list 加 `010_sites.sql`
- **`agents/admin_server.py` 改動**：
  - `GET /api/projects` / `GET /api/projects/<id>`：LEFT JOIN sites、回應的 `gps_lat / gps_lng / gps_radius_m / nas_path` 從 sites 取（找不到 sites 時退回 projects 本身欄位作 back-compat）；API response 欄位名與位置 **完全不變**
  - `POST /api/projects`：建 project 前 upsert sites（從 body 的 owner_name + site_name + gps + nas_path），把 site_id 寫到 projects；projects 上的 GPS/nas_path 欄位**也照寫一份**（back-compat、下個 release 才停）
  - `PUT /api/projects/<id>`：把 body 拆兩段 — project-level 欄位（name / status / notes / trello_board_id / project_type / owner_name / site_name）走原本的 projects update；site-level 欄位（gps_lat / gps_lng / gps_radius_m / nas_path）寫到該 project 對應的 sites row（自動讓同案場其他 project rows 一起看到新值）；若 owner_name / site_name 改了 → 重 upsert sites + 改 projects.site_id；同步寫一份到 projects 欄位作 back-compat
  - admin UI dialog 的 GPS 區塊與 NAS 路徑區塊加 hint：「此欄位屬於案場（業主-案場）。同案場不同 project type 共用」
- **端對端驗證**：改 `劉正群-龜山鉅力高宇C6-室內裝修` 的 GPS → 確認 `-設計` 那 row 立刻有 GPS；改 `陳永華-創世紀M3-室內裝修` → `-設計` 一起亮；新增無 GPS 全新案場 → 確認 sites row 也建出來

## Capabilities

### New Capabilities
（無 — 透過修改 `project-registry` 既有 capability 來反映規範化）

### Modified Capabilities
- `project-registry`：擴充 schema（新 `sites` 子實體）、修改 CRUD 行為（site-level 欄位寫到 sites、API response 從 JOIN 取），新增 site upsert 與 propagation 行為的 Scenarios

## Impact

- **linebot repo**：1 個 migration、`admin_server.py` 中 6 個 handler（list/get/create/update projects + helper）、`templates/admin.html` 的 dialog 加 hint
- **synophoto repo**：0 改動（API response 結構不變、linebot_client 不需 patch）
- **資料**：production 6 個 sites row 預計被建（看當下幾個 owner-site 組合）；既有 7 個 projects 全部填上 site_id
- **back-compat**：projects 上 gps_* / nas_path 4 個 column 暫不刪、繼續同步寫；確認沒有外部消費者讀 projects 那邊的欄位後，下個小 change 才 drop
- **rollback**：回退到前一個 digest 仍可運作（API 回應走 projects 欄位）；DB 結構變更不能 rollback、但因為新欄位都 nullable 也不會卡舊版

## Out of Scope

- 砍 projects 上 gps_* / nas_path 4 個 column（下次小 change）
- linebot admin UI 重新設計 layout（本次只加 hint）
- synophoto 端任何改動
- 把 photo_folder 變實體欄位（沿用 derived 邏輯 `{owner_name}-{site_name}`）
- owner_name / site_name rename 自動合併 sites（rename 等於使用者自負）
