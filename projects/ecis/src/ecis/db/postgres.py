"""Optional PostgreSQL backend. SQLite remains the default local store."""

from __future__ import annotations

import os
from typing import Any


def database_url() -> str:
    return os.getenv("DATABASE_URL", "")


def postgres_enabled() -> bool:
    return bool(database_url())


def connect_postgres():
    """Open a pooled psycopg2 connection when DATABASE_URL is set."""
    from ecis.db.pool import get_pool

    pool = get_pool()
    if pool is None:
        url = database_url()
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        import psycopg2

        return psycopg2.connect(url)
    return pool.getconn()


def copy_sqlite_table(name: str, rows: list[dict[str, Any]], columns: list[str]) -> int:
    if not postgres_enabled() or not rows:
        return 0
    from ecis.db.pool import pooled_connection

    with pooled_connection() as conn:
        cur = conn.cursor()
        placeholders = ",".join(["%s"] * len(columns))
        col_sql = ",".join(columns)
        cur.executemany(
            f"INSERT INTO {name} ({col_sql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
            [tuple(row.get(c) for c in columns) for row in rows],
        )
        conn.commit()
        n = cur.rowcount
        cur.close()
    return n
