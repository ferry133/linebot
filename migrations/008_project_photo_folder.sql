-- 008_project_photo_folder.sql
-- Add structured fields for project naming so downstream consumers
-- (synology-photo-tagger) can derive a stable photo_folder = "{owner}-{site}"
-- across the multi-到-1 relationship of (linebot project) → (NAS folder).
--
-- See openspec change `linebot-photo-folder` for context.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS owner_name   TEXT,
    ADD COLUMN IF NOT EXISTS site_name    TEXT,
    ADD COLUMN IF NOT EXISTS project_type TEXT;

ALTER TABLE projects
    DROP CONSTRAINT IF EXISTS projects_type_chk;

ALTER TABLE projects
    ADD CONSTRAINT projects_type_chk
    CHECK (project_type IS NULL
        OR project_type IN ('設計', '結構基礎', '室內裝修', '軟裝'));
