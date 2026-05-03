import os
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
