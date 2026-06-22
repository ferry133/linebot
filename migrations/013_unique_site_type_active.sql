-- 013_unique_site_type_active.sql
-- The public-facing project label is `{site_name}-{project_type}` (no owner name,
-- see openspec change `project-public-label`). To keep that label unambiguous,
-- enforce that no two *active* projects share the same (site_name, project_type).
-- Partial unique index (active only; completed/archived are exempt, matching the
-- case_number "no gap filling" style). NULL site_name/project_type are excluded.
--
-- Idempotent: CREATE UNIQUE INDEX IF NOT EXISTS.
-- NOTE: build fails if a duplicate already exists — pre-flight checked clean.

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_site_type_active
    ON projects (site_name, project_type)
    WHERE status = 'active'
      AND site_name IS NOT NULL
      AND project_type IS NOT NULL;
