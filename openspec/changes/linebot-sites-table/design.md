## Context

歷史軌跡：
- `005_projects.sql`（初始）建立 projects table，含 `nas_path` — 那時還沒有 owner / site 概念，nas_path 是 per-project 概念
- `008_project_photo_folder.sql`（linebot-photo-folder change）加 `owner_name / site_name / project_type` 三欄 + photo_folder derived 邏輯。**這時就出現第一次重複**：同案場不同 type 的 NAS path 已經是同一個值，但要在多 row 各填一次
- `009_project_gps.sql`（consolidate-project-registry change）加 `gps_lat / gps_lng / gps_radius_m` 三欄。**這時重複擴大到 GPS**
- 沒有任何正規化 — 因為當時急著上線、且只有 1 個案場，重複 cost 隱形

實測 production 7 個 projects（screenshot）：
- 曾宇晟-大宅天景 × 3 type → 共用同 nas_path，現在 3 row 都已填 GPS（透過 migration 010 寫入腳本）
- 劉正群-龜山鉅力高宇C6 × 2 type → 共用同 nas_path，只有 `-室內裝修` row 填了 GPS，`-設計` row 空白
- 陳永華-創世紀M3 × 2 type → 共用同 nas_path，只有 `-設計` row 填了 GPS，`-室內裝修` row 空白

合理的正規化：site = (owner_name, site_name) 唯一案場識別；site-level fields = `nas_path` + GPS 三欄。project = site + type。

## Goals / Non-Goals

**Goals:**
- 同案場不同 project_type 共用 site-level 欄位（GPS / NAS path），admin UI 一次填、自動 propagate
- API response 結構**完全不變**，synophoto 端 0 改動
- migration 安全 + idempotent（跑兩次結果一樣、不掉資料）
- back-compat 期間（1 release）projects 上的 4 個欄位繼續寫入，避免任何外部 reader 突然抓不到值

**Non-Goals:**
- 刪掉 projects 上的 gps_* / nas_path 4 個欄位（留下次小 change）
- admin UI 大改版（只加 hint）
- 處理 owner_name / site_name rename（rename 不在 supported workflow）

## Decisions

### D1. 新 sites table 的 schema

```sql
CREATE TABLE IF NOT EXISTS sites (
    id            BIGSERIAL PRIMARY KEY,
    owner_name    TEXT NOT NULL,
    site_name     TEXT NOT NULL,
    gps_lat       REAL,
    gps_lng       REAL,
    gps_radius_m  INTEGER DEFAULT 50,
    nas_path      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_name, site_name)
);
```

理由：
- BIGSERIAL：sites 表是常 join 的 hot table、整數 key 簡單快
- UNIQUE (owner_name, site_name)：兩欄都 NOT NULL → 真正的 unique constraint（不需 partial index）
- GPS 三欄 nullable + 沿用 `009` 的 CHECK 條件（拼成 `sites_gps_chk`）
- nas_path nullable（admin 可能還沒設）

projects 表加：
```sql
ALTER TABLE projects ADD COLUMN IF NOT EXISTS site_id BIGINT REFERENCES sites(id);
CREATE INDEX IF NOT EXISTS projects_site_id_idx ON projects(site_id);
```

site_id nullable：legacy row（沒填 owner_name / site_name）保持 NULL

### D2. Migration 010 的 data backfill 演算法

```sql
-- 1. 為所有 (owner_name, site_name) 兩欄都非 null 的 projects 建 sites row
INSERT INTO sites (owner_name, site_name)
SELECT DISTINCT owner_name, site_name
FROM projects
WHERE owner_name IS NOT NULL AND site_name IS NOT NULL
ON CONFLICT (owner_name, site_name) DO NOTHING;

-- 2. 從 projects 反向 backfill sites 的 nas_path / gps_*：取「有 GPS」的優先、若都有取最新
WITH ranked AS (
    SELECT p.owner_name, p.site_name, p.nas_path, p.gps_lat, p.gps_lng, p.gps_radius_m, p.updated_at,
           ROW_NUMBER() OVER (
               PARTITION BY p.owner_name, p.site_name
               ORDER BY (CASE WHEN p.gps_lat IS NOT NULL THEN 0 ELSE 1 END),
                        p.updated_at DESC NULLS LAST
           ) AS rn
    FROM projects p
    WHERE p.owner_name IS NOT NULL AND p.site_name IS NOT NULL
)
UPDATE sites s
SET nas_path    = COALESCE(s.nas_path, r.nas_path),
    gps_lat     = COALESCE(s.gps_lat, r.gps_lat),
    gps_lng     = COALESCE(s.gps_lng, r.gps_lng),
    gps_radius_m = COALESCE(s.gps_radius_m, r.gps_radius_m),
    updated_at = now()
FROM ranked r
WHERE r.rn = 1
  AND s.owner_name = r.owner_name
  AND s.site_name  = r.site_name;

-- 3. 把 site_id 回填到 projects
UPDATE projects p
SET site_id = s.id
FROM sites s
WHERE p.owner_name = s.owner_name
  AND p.site_name  = s.site_name
  AND p.site_id IS NULL;
```

**Idempotent 性**：
- Step 1：`ON CONFLICT DO NOTHING` 第二次跑不會塞重複
- Step 2：`COALESCE(s.xxx, r.xxx)` — 已有值不覆蓋（避免 admin 手動清空 sites 後被 migration 又寫回）
- Step 3：`p.site_id IS NULL` 過濾，已 link 的不動

**邊界 case**：
- 既有 projects 中 `gps_lat IS NULL` 的 row：第二次 migration 跑時，sites 上對應欄位已是已填值（或都 null），COALESCE 不改變
- 既有 admin 在 sites 上改了 GPS 後再跑 migration：COALESCE 保留 sites 的 value
- legacy projects（owner_name / site_name 任一為 null）：完全不參與 migration

### D3. API write path 設計

**`POST /api/projects`**：
1. 從 body 取 owner_name + site_name + (gps_*, nas_path)
2. 若 owner_name 與 site_name **都非 null**：upsert 進 sites（用 `INSERT ... ON CONFLICT (owner_name, site_name) DO UPDATE SET ...` 帶 GPS / nas_path），抓回 site_id
3. 若任一 null：site_id = NULL
4. INSERT projects row、同時把 site_id 設好；GPS / nas_path 也照寫進 projects 欄位（back-compat）

**`PUT /api/projects/<id>`** — 拆兩段：
1. 從 body 識別 site-level 欄位（gps_lat / gps_lng / gps_radius_m / nas_path）與 project-level 欄位
2. 找 projects 當前對應的 site_id
3. 處理 owner_name / site_name 改名情境：
   - 若 PUT 帶了 owner_name 或 site_name 且改變了 → upsert 新 sites row、project.site_id 改指過去；舊 sites row **不刪**（可能還被別的 project 引用）
4. 若有 site-level 欄位且 project.site_id 非 null：UPDATE sites SET gps_*, nas_path（自動讓同 site 其他 projects 看到新值）
5. 若 site_id 為 null（legacy）但 PUT 帶了 site-level 欄位：upsert 一個 site 並 link
6. UPDATE projects 處理 project-level 欄位 + 同步寫 gps_* / nas_path 到 projects（back-compat）

**Why 還要寫 projects 那一份？** Back-compat：當前 release 沒人讀 sites 以外的版本，但若有任何 cached client 還在直接讀 projects 表（不太可能、但保險），他們仍能看到一致資料。下一個 release drop 的時候才放心拿掉。

### D4. API read path 設計

```sql
-- GET /api/projects (list)
SELECT p.*,
       COALESCE(s.gps_lat,      p.gps_lat)      AS gps_lat,
       COALESCE(s.gps_lng,      p.gps_lng)      AS gps_lng,
       COALESCE(s.gps_radius_m, p.gps_radius_m) AS gps_radius_m,
       COALESCE(s.nas_path,     p.nas_path)     AS nas_path
FROM projects p
LEFT JOIN sites s ON s.id = p.site_id
```

COALESCE 順序「sites 優先、projects fallback」：
- 正常情況：sites 有值
- 過渡期：projects 還寫一份、sites 也寫一份 → sites 取得（一致）
- legacy row：sites 沒值 / 沒 site_id → fallback 到 projects（既有行為）

### D5. UNIQUE constraint 怎麼處理 PUT 改名後的衝突

PUT 改 owner_name / site_name 到「已存在的另一個 site」會 collide。處理：
- upsert（`ON CONFLICT DO UPDATE SET ...` 配 update 一個無害的欄位 like `updated_at = now()`）→ 回 sites.id 不變，自動合併
- project.site_id 改指該已存在的 site
- 這等於「移動 project 到別的 site」，admin 預期行為

不處理：原 sites row 變孤兒（其他 project 不再引用）→ 暫留 DB、不刪。下次清理性 change 可能加自動 GC。

### D6. UI 改動最小化

admin dialog 在 GPS 區塊與 NAS path 區塊上方加 hint 文字：

```html
<div class="hint" style="font-size:11px;color:#888;margin-bottom:4px">
  ⚙️ 此欄位屬於「案場」（業主-案場）。同案場不同 project type 共用同一組值。
</div>
```

不改 layout、不改 input、不改 JS 邏輯（PUT body 仍含這些欄位，backend 拆兩段處理）。

### D7. nas_path 也納入正規化嗎？

是。理由：實測 `劉正群-龜山鉅力高宇C6-設計` 與 `-室內裝修` 兩 row 的 nas_path 完全一樣（`/mnt/nas/jia.homedesign/00. 執行中案場/114年，第15案,...`）— 這是 site-level 屬性。

含義：admin 改一個 project 的 nas_path → 同案場其他 project 也立刻指到新 path。這也是使用者預期。

## Risks / Trade-offs

- [風險] Migration 010 跑壞 → 既有 7 個 projects 全部丟 GPS
  → Mitigation: idempotent 設計（COALESCE 不覆蓋）+ 維持 projects 欄位作 back-compat（read path 二選一）；先在 staging 跑（或 prod 上 backup DB 後再跑）

- [風險] sites table 變孤兒 row（rename / 解綁後）
  → Mitigation: 不做自動 GC；管理員可手動清，下次正式 sites-table-gc change 加自動

- [風險] PUT 同時改 owner_name 與 GPS：site upsert 與 GPS update 順序
  → Mitigation: design D3 步驟順序明定（先解決 site_id，再 update sites GPS）；任一 step 失敗 rollback transaction

- [風險] 雙寫 projects + sites 期間，某種競態下兩邊不同步
  → Mitigation: 所有寫都在同一個 transaction；read path COALESCE 把 sites 排第一、即使 projects 落後也以 sites 為準

- [風險] synophoto 已有 cache 的 linebot.projects.yaml 中沒含 site_id（不影響 LinebotProject 邏輯）
  → Mitigation: 完全不影響、synophoto 端不讀 site_id、本 change 沒打到 cache 結構

## Migration Plan

1. linebot repo commit + push（migration + admin_server + UI hint）
2. Build image, bump jg-base `linebot/app/admin.yaml` digest
3. Reconcile gitrepository jg-base + kustomization extras-linebot（兩個都要）
4. Pod 啟動跑 migration 010；觀察 log `[INFO] migration applied: 010_sites.sql`
5. 端對端驗證：
   - GET /api/projects 確認 7 筆都有 GPS（含原本 `-設計` / `-室內裝修` 空白的兩組）
   - PUT 某筆 `-室內裝修` 的 GPS 改個值 → GET 後該 site 所有 projects 都改了
   - POST 一筆全新案場 → sites + projects 都建出來
6. Rollback：回退 admin digest；DB 結構不能 rollback、但 nullable 設計讓舊 image 跑得起來

## Open Questions

無 — D1-D7 涵蓋了所有設計決策。實作時可能小細節調整（例：sites_gps_chk constraint 名稱、是否加 sites 上的 updated_at trigger），不影響 design 主結構。
