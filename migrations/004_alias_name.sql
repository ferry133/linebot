-- 004_alias_name.sql
-- Add alias_name to line_users for stable short identifier (Trello tags, etc.)

ALTER TABLE line_users
    ADD COLUMN IF NOT EXISTS alias_name TEXT UNIQUE;

-- Seed known aliases from display_name (lowercase match)
DO $$
DECLARE
    known_aliases TEXT[] := ARRAY['larry', 'sa', 'yan'];
    alias TEXT;
    matched_id TEXT;
BEGIN
    FOREACH alias IN ARRAY known_aliases LOOP
        SELECT line_id INTO matched_id
        FROM line_users
        WHERE lower(display_name) = alias
        LIMIT 1;

        IF matched_id IS NOT NULL THEN
            UPDATE line_users SET alias_name = alias WHERE line_id = matched_id;
            RAISE NOTICE 'alias_name set: % → %', alias, matched_id;
        ELSE
            RAISE WARNING 'alias_name migration: no user found for alias ''%''', alias;
        END IF;
    END LOOP;
END $$;
