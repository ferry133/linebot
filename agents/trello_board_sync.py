#!/usr/bin/env python3
"""
Trello Board Sync — 一次性任務（k8s CronJob 每天執行）

從 Trello workspace 拉取所有開啟的 board，
upsert 進 trello_boards 表，供 trello_agent 使用。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from shared.log import setup as _setup_log
_setup_log()

import logging
log = logging.getLogger(__name__)

from shared.db import db_exec
from trello_line_notifier import get_boards, WORKSPACE_ID


def sync():
    boards = get_boards()
    log.info(f"[board_sync] Fetched {len(boards)} boards from workspace {WORKSPACE_ID}")

    def _upsert(conn):
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM trello_boards WHERE workspace_id = %s",
                (WORKSPACE_ID,),
            )
            for b in boards:
                cur.execute(
                    """
                    INSERT INTO trello_boards (workspace_id, board_id, board_name, synced_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (workspace_id, board_id) DO UPDATE
                        SET board_name = EXCLUDED.board_name,
                            synced_at  = now()
                    """,
                    (WORKSPACE_ID, b["id"], b["name"]),
                )
        return len(boards)

    count = db_exec(_upsert)
    if count is None:
        log.error("[board_sync] DB write failed — check DATABASE_URL")
        sys.exit(1)
    log.info(f"[board_sync] Synced {count} boards to DB")


if __name__ == "__main__":
    sync()
