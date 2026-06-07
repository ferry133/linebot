-- 010_sites.sql
-- Normalize site-level fields (gps + nas_path) out of projects into a new
-- `sites` table keyed by (owner_name, site_name). After this migration the
-- same physical site shared by multiple project_type rows (e.g.
-- "曾宇晟-大宅天景-設計" and "曾宇晟-大宅天景-結構基礎") points at a single
-- sites row, so admins only ever fill GPS / NAS path once per site.
--
-- The four legacy columns (projects.gps_lat / gps_lng / gps_radius_m /
-- nas_path) are intentionally kept for one release as a back-compat copy
-- (read API does COALESCE(sites, projects); a later small change will drop
-- them once nobody depends on the projects-side copy).
--
-- Idempotent: re-running this script does not duplicate site rows or
-- overwrite values that an admin has since edited.
--
-- See openspec change `linebot-sites-table`.

-- ── 1. Schema ────────────────────────────────────────────────────────────

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

ALTER TABLE sites
    DROP CONSTRAINT IF EXISTS sites_gps_chk;

ALTER TABLE sites
    ADD CONSTRAINT sites_gps_chk
    CHECK (
        (gps_lat IS NULL AND gps_lng IS NULL)
        OR (
            gps_lat  BETWEEN -90.0  AND 90.0
            AND gps_lng  BETWEEN -180.0 AND 180.0
            AND gps_radius_m IS NOT NULL
            AND gps_radius_m BETWEEN 1 AND 5000
        )
    );

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS site_id BIGINT REFERENCES sites(id);

CREATE INDEX IF NOT EXISTS projects_site_id_idx ON projects(site_id);

-- ── 2. Data backfill (idempotent) ────────────────────────────────────────

-- 2a. Create one sites row per distinct (owner_name, site_name) where both
--     columns are non-null. Existing rows are left alone.
INSERT INTO sites (owner_name, site_name)
SELECT DISTINCT owner_name, site_name
  FROM projects
 WHERE owner_name IS NOT NULL
   AND site_name  IS NOT NULL
ON CONFLICT (owner_name, site_name) DO NOTHING;

-- 2b. Backfill site-level values from the projects row that's most likely
--     to have the canonical GPS / nas_path:
--       - Prefer rows that *have* gps_lat set (NULL goes last)
--       - Tie-break by most recent updated_at
--     COALESCE(sites.col, ranked.col) ensures values an admin has already
--     edited on a sites row are never overwritten by a stale projects row.
WITH ranked AS (
    SELECT p.owner_name,
           p.site_name,
           p.nas_path,
           p.gps_lat,
           p.gps_lng,
           p.gps_radius_m,
           ROW_NUMBER() OVER (
               PARTITION BY p.owner_name, p.site_name
               ORDER BY (CASE WHEN p.gps_lat IS NOT NULL THEN 0 ELSE 1 END),
                        p.updated_at DESC NULLS LAST
           ) AS rn
      FROM projects p
     WHERE p.owner_name IS NOT NULL
       AND p.site_name  IS NOT NULL
)
UPDATE sites s
   SET nas_path     = COALESCE(s.nas_path,     r.nas_path),
       gps_lat      = COALESCE(s.gps_lat,      r.gps_lat),
       gps_lng      = COALESCE(s.gps_lng,      r.gps_lng),
       gps_radius_m = COALESCE(s.gps_radius_m, r.gps_radius_m),
       updated_at   = CASE
                          WHEN s.nas_path IS NULL
                            OR s.gps_lat  IS NULL
                            OR s.gps_lng  IS NULL
                            OR s.gps_radius_m IS NULL
                          THEN now()
                          ELSE s.updated_at
                      END
  FROM ranked r
 WHERE r.rn = 1
   AND s.owner_name = r.owner_name
   AND s.site_name  = r.site_name;

-- 2c. Link each project to its corresponding sites row. Only rows where
--     site_id is still NULL are touched, so re-runs are a no-op once every
--     project is linked.
UPDATE projects p
   SET site_id = s.id
  FROM sites s
 WHERE p.owner_name IS NOT NULL
   AND p.site_name  IS NOT NULL
   AND p.site_id IS NULL
   AND p.owner_name = s.owner_name
   AND p.site_name  = s.site_name;
