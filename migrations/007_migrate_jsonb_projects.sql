-- 007_migrate_jsonb_projects.sql
-- Migrate line_users.projects JSONB (board_name strings) → projects + line_user_projects tables.
-- Orphan board_names (no match in trello_boards) get WARNING log.

DO $$
DECLARE
    rec       RECORD;
    bname     TEXT;
    board_id  TEXT;
    proj_id   UUID;
    yr        INT;
    seq       INT;
    case_num  TEXT;
BEGIN
    FOR rec IN
        SELECT line_id, jsonb_array_elements_text(projects) AS raw_name
        FROM line_users
        WHERE jsonb_array_length(projects) > 0
    LOOP
        bname := trim(rec.raw_name);

        -- Look up board_id from trello_boards
        SELECT tb.board_id INTO board_id
        FROM trello_boards tb
        WHERE tb.board_name = bname
        LIMIT 1;

        -- Check if a project record already exists for this board_id/name
        IF board_id IS NOT NULL THEN
            SELECT p.project_id INTO proj_id
            FROM projects p
            WHERE p.trello_board_id = board_id
            LIMIT 1;
        ELSE
            SELECT p.project_id INTO proj_id
            FROM projects p
            WHERE p.name = bname AND p.trello_board_id IS NULL
            LIMIT 1;
        END IF;

        -- Create project if not exists
        IF proj_id IS NULL THEN
            yr := extract(year FROM now())::INT - 1911;
            SELECT coalesce(max(
                (regexp_match(p.case_number, '(\d+)案$'))[1]::INT
            ), 0) + 1 INTO seq
            FROM projects p
            WHERE p.case_number LIKE yr || '年%';

            case_num := yr || '年第' || seq || '案';

            IF board_id IS NULL THEN
                RAISE WARNING 'migrate_jsonb_projects: no board_id for ''%'' (line_id: %), creating orphan project', bname, rec.line_id;
            END IF;

            INSERT INTO projects (case_number, name, trello_board_id, status)
            VALUES (case_num, bname, board_id, 'active')
            RETURNING project_id INTO proj_id;
        END IF;

        -- Create line_user_projects if not exists
        INSERT INTO line_user_projects (line_id, project_id, relation)
        VALUES (rec.line_id, proj_id, 'customer')
        ON CONFLICT (line_id, project_id) DO NOTHING;
    END LOOP;
END $$;
