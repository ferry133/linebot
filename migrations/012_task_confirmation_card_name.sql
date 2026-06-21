-- 012_task_confirmation_card_name.sql
-- Snapshot the Trello card name at claim time so the batched/on-demand
-- supervisor confirmation card can show project + card context for locating
-- the to-do, without re-fetching each card from Trello at render time.
-- See openspec change `supervisor-confirm-card-context`.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run.

ALTER TABLE task_confirmations
    ADD COLUMN IF NOT EXISTS card_name TEXT;
