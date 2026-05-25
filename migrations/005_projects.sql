-- 005_projects.sql
-- Project entity table: stable UUID anchor for Trello board + NAS folder + users.

CREATE TABLE IF NOT EXISTS projects (
    project_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number     TEXT NOT NULL UNIQUE,        -- e.g. "115年第3案"
    name            TEXT NOT NULL,
    trello_board_id TEXT,                        -- nullable for historical projects
    nas_path        TEXT,                        -- set after NAS provisioning
    status          TEXT NOT NULL DEFAULT 'active',  -- active | completed | archived
    notes           TEXT,
    started_at      DATE,
    completed_at    DATE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
-- status: active | completed | archived
