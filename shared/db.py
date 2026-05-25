import os
import pathlib
import threading

import psycopg2
import psycopg2.pool

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> psycopg2.pool.ThreadedConnectionPool | None:
    global _pool
    if _pool is not None:
        return _pool
    if not DATABASE_URL:
        return None
    with _lock:
        if _pool is None:
            try:
                _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DATABASE_URL)
                print("[INFO] DB pool initialized")
            except Exception as e:
                print(f"[WARN] DB pool init failed: {e}")
    return _pool


MIGRATIONS = [
    "001_init.sql",
    "002_trello_boards.sql",
    "003_line_users.sql",
    "004_alias_name.sql",
    "005_projects.sql",
    "006_line_user_projects.sql",
    "007_migrate_jsonb_projects.sql",
]

_MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "migrations"


def run_migrations() -> None:
    pool = get_pool()
    if not pool:
        print("[WARN] run_migrations: no DB pool, skipping")
        return
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
            )
            conn.commit()
            for fname in MIGRATIONS:
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename=%s", (fname,))
                if cur.fetchone():
                    continue
                sql_path = _MIGRATIONS_DIR / fname
                if not sql_path.exists():
                    print(f"[WARN] migration file not found: {sql_path}")
                    continue
                sql = sql_path.read_text()
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (fname,))
                conn.commit()
                print(f"[INFO] migration applied: {fname}")
    except Exception as e:
        print(f"[WARN] run_migrations error: {e}")
        conn.rollback()
    finally:
        pool.putconn(conn)


def db_exec(fn):
    """Run fn(conn) with a pooled connection; return None on error."""
    pool = get_pool()
    if not pool:
        return None
    conn = None
    try:
        conn = pool.getconn()
        result = fn(conn)
        conn.commit()
        return result
    except Exception as e:
        print(f"[WARN] DB error: {e}")
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return None
    finally:
        if conn:
            try:
                pool.putconn(conn)
            except Exception:
                pass
