"""JSON provenance chain from raw file through triangulation."""

from __future__ import annotations

import json
from typing import Any

from ecis.db.init_db import get_connection


def build_lineage(
    *,
    ticker: str,
    source_file: str,
    chunk_index: int,
    category: str | None,
    keyword: dict | None,
    finbert: dict | None,
    llm: dict | None,
    conflict: dict | None,
    weights: dict | None,
    dedup: str | None = None,
) -> str:
    chain = {
        "raw_file": source_file,
        "ticker": ticker,
        "chunk_index": chunk_index,
        "escalation_category": category,
        "fast_pass": {"keyword": keyword, "finbert": finbert},
        "llm": llm,
        "conflict_resolution": conflict,
        "triangulation_weights": weights,
        "deduplication": dedup,
    }
    return json.dumps(chain, default=str)


def write_lineage_for_signals(ticker: str | None = None) -> int:
    """Backfill lineage from existing columns when a live chain was not stored."""
    conn = get_connection("signals")
    query = "SELECT signal_id, ticker, chunk_index, source_method, llm_model, provenance, lineage FROM signals"
    params: list[str] = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())
    rows = conn.execute(query, params).fetchall()
    n = 0
    for row in rows:
        if row["lineage"]:
            continue
        blob = build_lineage(
            ticker=row["ticker"],
            source_file="",
            chunk_index=row["chunk_index"],
            category=None,
            keyword=None,
            finbert=None,
            llm={"model": row["llm_model"], "source_method": row["source_method"]},
            conflict=None,
            weights=None,
            dedup=None,
        )
        try:
            conn.execute("UPDATE signals SET lineage = ? WHERE signal_id = ?", (blob, row["signal_id"]))
        except Exception:
            break
        n += 1
    conn.commit()
    conn.close()
    return n


def latest_lineage(signal_id: int) -> dict[str, Any] | None:
    conn = get_connection("signals")
    try:
        row = conn.execute(
            "SELECT lineage, provenance FROM signals WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()
    if not row:
        return None
    raw = row["lineage"] or row["provenance"]
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}
