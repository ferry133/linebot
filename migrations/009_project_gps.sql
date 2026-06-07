-- 009_project_gps.sql
-- Move ownership of GPS coordinates (center + radius) from synology-photo-tagger's
-- on-disk YAML registry into linebot.projects, so that linebot becomes the sole
-- source of truth for project metadata.
--
-- All three columns are nullable: existing 7 projects do not yet have GPS data,
-- and not every future project will have meaningful GPS (e.g. paperwork-only cases).
-- The tagger MUST skip rows where gps_lat IS NULL during haversine matching.
--
-- See openspec change `consolidate-project-registry` for context.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS gps_lat      REAL,
    ADD COLUMN IF NOT EXISTS gps_lng      REAL,
    ADD COLUMN IF NOT EXISTS gps_radius_m INTEGER DEFAULT 50;

ALTER TABLE projects
    DROP CONSTRAINT IF EXISTS projects_gps_chk;

ALTER TABLE projects
    ADD CONSTRAINT projects_gps_chk
    CHECK (
        (gps_lat IS NULL AND gps_lng IS NULL)
        OR (
            gps_lat  BETWEEN -90.0  AND 90.0
            AND gps_lng  BETWEEN -180.0 AND 180.0
            AND gps_radius_m IS NOT NULL
            AND gps_radius_m BETWEEN 1 AND 5000
        )
    );
