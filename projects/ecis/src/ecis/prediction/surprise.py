"""Guidance surprise: extracted direction vs street consensus at the call."""

from __future__ import annotations

from typing import Any

from ecis.db.init_db import get_connection
from ecis.prediction.consensus import consensus_delta, consensus_direction


def surprise_value(extracted: str, consensus: str) -> float:
    order = {"lowered": 0, "maintained": 1, "raised": 2}
    return abs(order.get(extracted, 1) - order.get(consensus, 1)) / 2.0


def link_surprise(ticker: str | None = None) -> dict[str, Any]:
    conn = get_connection("signals")
    query = "SELECT signal_id, ticker, direction FROM signals"
    params: list[str] = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())
    rows = conn.execute(query, params).fetchall()
    n = 0
    by = {"high": 0, "low": 0}
    for row in rows:
        delta = consensus_delta(row["ticker"])
        expected = consensus_direction(delta)
        score = surprise_value(row["direction"], expected)
        conn.execute("UPDATE signals SET surprise_score = ? WHERE signal_id = ?", (score, row["signal_id"]))
        n += 1
        by["high" if score >= 0.5 else "low"] += 1
    conn.commit()
    conn.close()
    return {"labelled": n, **by}
