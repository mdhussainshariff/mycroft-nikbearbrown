"""psycopg2 connection pool used when DATABASE_URL is set."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from ecis.config.settings import settings
from ecis.db.postgres import database_url, postgres_enabled

logger = logging.getLogger(__name__)

_pool = None


def get_pool():
    global _pool
    if not postgres_enabled():
        return None
    if _pool is None:
        from psycopg2.pool import ThreadedConnectionPool

        _pool = ThreadedConnectionPool(
            settings.pg_pool_min,
            settings.pg_pool_max,
            dsn=database_url(),
        )
        logger.info(
            "Postgres pool min=%s max=%s idle=%ss",
            settings.pg_pool_min,
            settings.pg_pool_max,
            settings.pg_pool_idle_seconds,
        )
    return _pool


@contextmanager
def pooled_connection() -> Iterator:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL is not set")
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def pool_status() -> dict:
    pool = get_pool()
    if pool is None:
        return {"enabled": False, "min": settings.pg_pool_min, "max": settings.pg_pool_max}
    return {
        "enabled": True,
        "min": settings.pg_pool_min,
        "max": settings.pg_pool_max,
        "idle_timeout_seconds": settings.pg_pool_idle_seconds,
    }
