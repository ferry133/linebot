-- 003_line_users.sql
-- LINE user registry with role-based access control.

CREATE TABLE IF NOT EXISTS line_users (
    line_id      TEXT PRIMARY KEY,
    display_name TEXT,
    picture_url  TEXT,
    role         TEXT NOT NULL DEFAULT 'visitor',
    projects     JSONB NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now()
);
-- role: admin | employee | vendor | customer | visitor
-- projects: ignored for admin/employee; board name list for vendor/customer; [] for visitor
