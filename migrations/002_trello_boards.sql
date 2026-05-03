-- 002_trello_boards.sql
-- Board name ↔ ID mapping, synced daily from Trello workspace.

CREATE TABLE IF NOT EXISTS trello_boards (
    workspace_id  TEXT NOT NULL,
    board_id      TEXT NOT NULL,
    board_name    TEXT NOT NULL,
    synced_at     TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (workspace_id, board_id)
);
