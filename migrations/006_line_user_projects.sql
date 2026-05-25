-- 006_line_user_projects.sql
-- Many-to-many: LINE user ↔ project with relation type.

CREATE TABLE IF NOT EXISTS line_user_projects (
    line_id    TEXT NOT NULL REFERENCES line_users(line_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    relation   TEXT NOT NULL DEFAULT 'customer',  -- customer | vendor
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (line_id, project_id)
);
