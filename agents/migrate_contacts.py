#!/usr/bin/env python3
"""
One-time migration: contacts.json -> line_users DB table.

  projects = "*"   -> role = employee
  projects = [...] -> role = customer
  ON CONFLICT (line_id) DO NOTHING -- never overwrite existing records.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from shared.db import db_exec

CONTACTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "knowledge", "contacts.json"
)


def migrate():
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            contacts = json.load(f)
    except OSError as e:
        print(f"[migrate] Cannot read contacts.json: {e}")
        sys.exit(1)

    inserted = 0
    skipped = 0

    for name, v in contacts.items():
        if isinstance(v, dict):
            line_id = v.get("line_id", "").strip()
            projects_raw = v.get("projects", "*")
        else:
            line_id = str(v).strip()
            projects_raw = "*"

        if not line_id:
            continue

        if projects_raw == "*":
            role = "employee"
            projects = []
        else:
            role = "customer"
            projects = projects_raw if isinstance(projects_raw, list) else []

        def _insert(conn, _line_id=line_id, _name=name, _role=role, _projects=projects):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO line_users (line_id, display_name, role, projects)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (line_id) DO NOTHING
                    """,
                    (_line_id, _name, _role, json.dumps(_projects)),
                )
                return cur.rowcount

        rows = db_exec(_insert)
        if rows == 1:
            print(f"[migrate] Inserted: {name} ({line_id[:8]}) role={role}")
            inserted += 1
        else:
            print(f"[migrate] Skipped (already exists): {name}")
            skipped += 1

    print(f"\n[migrate] Done -- inserted={inserted}, skipped={skipped}")


if __name__ == "__main__":
    migrate()
