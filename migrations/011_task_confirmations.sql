-- 011_task_confirmations.sql
-- Vendor-claimed Trello completion changes that await supervisor ratification
-- (事後追認). A 廠商 (task owner who is not admin/employee) marking a work item
-- complete/uncomplete via the LINE reminder buttons takes effect in Trello
-- immediately (provisional) and inserts a `pending` row here; a supervisor
-- later confirms (定案) or rejects (還原 Trello). See openspec change
-- `trello-task-status-update`.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS; safe to re-run.

CREATE TABLE IF NOT EXISTS task_confirmations (
    id               BIGSERIAL PRIMARY KEY,
    board_id         TEXT NOT NULL,
    card_id          TEXT NOT NULL,
    checkitem_id     TEXT,                 -- NULL for card-level (dueComplete) items
    source           TEXT NOT NULL,        -- 'card' | 'checklist'
    label            TEXT NOT NULL,        -- work-item label for display
    target_state     TEXT NOT NULL,        -- 'complete' | 'incomplete' (what the vendor claimed)
    claimer_user_id  TEXT NOT NULL,
    claimer_alias    TEXT,
    claimed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    status           TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'confirmed' | 'rejected'
    confirmer_user_id TEXT,
    resolved_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_task_confirmations_status
    ON task_confirmations (status);
