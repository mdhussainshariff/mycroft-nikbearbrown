"""SQLite stand-ins for the Phase 13 materialized views."""

from __future__ import annotations

from ecis.db.init_db import get_connection


def refresh_views() -> dict[str, int]:
    conn = get_connection("agents")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS mv_reader_brier (
            source_method TEXT PRIMARY KEY,
            n INTEGER,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS mv_ticker_volume (
            ticker TEXT,
            quarter TEXT,
            n INTEGER,
            PRIMARY KEY (ticker, quarter)
        );
        DELETE FROM mv_reader_brier;
        DELETE FROM mv_ticker_volume;
        """
    )
    conn.commit()
    conn.close()

    conn_s = get_connection("signals")
    readers = conn_s.execute(
        "SELECT source_method, COUNT(*) AS n FROM signals GROUP BY source_method"
    ).fetchall()
    volumes = conn_s.execute(
        """SELECT ticker, substr(transcript_date, 1, 7) AS quarter, COUNT(*) AS n
           FROM signals GROUP BY ticker, quarter"""
    ).fetchall()
    conn_s.close()

    conn = get_connection("agents")
    conn.executemany(
        "INSERT OR REPLACE INTO mv_reader_brier (source_method, n, updated_at) VALUES (?, ?, datetime('now'))",
        [(r["source_method"], r["n"]) for r in readers],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO mv_ticker_volume (ticker, quarter, n) VALUES (?, ?, ?)",
        [(r["ticker"], r["quarter"], r["n"]) for r in volumes],
    )
    conn.commit()
    conn.close()
    return {"readers": len(readers), "ticker_quarters": len(volumes)}
