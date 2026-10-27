"""Slow-query logging and EXPLAIN for frequent dashboard statements."""

from __future__ import annotations

import time
from typing import Any

from ecis.config.settings import settings
from ecis.db.init_db import get_connection

DASHBOARD_QUERIES = {
    "signals_by_ticker": "SELECT ticker, COUNT(*) AS n FROM signals GROUP BY ticker",
    "reader_counts": "SELECT source_method, COUNT(*) AS n FROM signals GROUP BY source_method",
    "recent_signals": "SELECT signal_id, ticker, direction, confidence_raw FROM signals ORDER BY created_at DESC LIMIT 50",
}


def log_query(name: str, elapsed_ms: float, used_index: bool | None = None, note: str = "") -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO query_stats (query_name, elapsed_ms, used_index, note)
           VALUES (?, ?, ?, ?)""",
        (name, elapsed_ms, None if used_index is None else int(used_index), note),
    )
    conn.commit()
    conn.close()


def time_sql(name: str, sql: str, db: str = "signals") -> dict[str, Any]:
    conn = get_connection(db)
    start = time.perf_counter()
    rows = conn.execute(sql).fetchall()
    elapsed = (time.perf_counter() - start) * 1000
    plan_note = ""
    used_index = None
    try:
        plan = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
        plan_note = " | ".join(str(dict(p)) for p in plan)
        used_index = any("USING INDEX" in str(p).upper() or "INDEX" in str(p).upper() for p in plan)
    except Exception:
        pass
    conn.close()
    log_query(name, elapsed, used_index, plan_note[:500])
    slow = elapsed >= settings.slow_query_ms
    return {
        "name": name,
        "elapsed_ms": round(elapsed, 3),
        "n": len(rows),
        "slow": slow,
        "used_index": used_index,
        "plan": plan_note,
    }


def audit_dashboard_queries() -> list[dict[str, Any]]:
    reports = []
    for name, sql in DASHBOARD_QUERIES.items():
        reports.append(time_sql(name, sql))
    return reports
