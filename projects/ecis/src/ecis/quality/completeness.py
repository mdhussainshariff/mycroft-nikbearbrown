"""Per-ticker gaps: consensus, prices, Chroma, and overdue outcomes."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ecis.config.settings import settings
from ecis.db.init_db import get_connection


def _tickers() -> list[str]:
    conn = get_connection("agents")
    try:
        rows = conn.execute("SELECT ticker FROM tickers ORDER BY ticker").fetchall()
    except Exception:
        rows = []
    conn.close()
    if rows:
        return [r["ticker"] for r in rows]
    conn_s = get_connection("signals")
    sigs = conn_s.execute("SELECT DISTINCT ticker FROM signals").fetchall()
    conn_s.close()
    return [r["ticker"] for r in sigs]


def _has_chunk_files(ticker: str) -> bool:
    root = Path(settings.chunks_dir) / ticker
    if root.exists() and any(root.rglob("*.json")):
        return True
    return False


def _has_chroma(ticker: str) -> bool:
    try:
        from ecis.embedding.embedder import get_transcript_collection

        col = get_transcript_collection()
        got = col.get(where={"ticker": ticker}, limit=1)
        return bool(got.get("ids"))
    except Exception:
        return _has_chunk_files(ticker)


def _has_prices(ticker: str) -> bool:
    conn = get_connection("agents")
    try:
        row = conn.execute(
            "SELECT 1 FROM market_prices WHERE ticker = ? LIMIT 1", (ticker,)
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    return row is not None


def _missing_outcomes(ticker: str, horizon: int = 30) -> int:
    cutoff = (date.today() - timedelta(days=horizon)).isoformat()
    conn_s = get_connection("signals")
    signals = conn_s.execute(
        "SELECT signal_id, transcript_date FROM signals WHERE ticker = ?",
        (ticker,),
    ).fetchall()
    conn_s.close()
    due = [r["signal_id"] for r in signals if (r["transcript_date"] or "") <= cutoff]
    if not due:
        return 0
    conn_o = get_connection("outcomes")
    try:
        resolved = {
            r["signal_id"]
            for r in conn_o.execute(
                "SELECT DISTINCT signal_id FROM outcomes WHERE correct IS NOT NULL"
            ).fetchall()
        }
    except Exception:
        resolved = set()
    conn_o.close()
    return sum(1 for sid in due if sid not in resolved)


def report_completeness(batch_id: str = "latest") -> list[dict[str, Any]]:
    reports = []
    conn = get_connection("agents")
    for ticker in _tickers():
        missing_consensus = 0 if settings.fmp_api_key else 1
        missing_prices = 0 if _has_prices(ticker) else 1
        missing_chroma = 0 if _has_chroma(ticker) else 1
        missing_outcomes = _missing_outcomes(ticker)
        notes = {
            "batch_id": batch_id,
            "has_fmp_key": bool(settings.fmp_api_key),
            "chunk_files": _has_chunk_files(ticker),
        }
        conn.execute(
            """INSERT INTO completeness_reports
               (ticker, missing_consensus, missing_prices, missing_chroma, missing_outcomes, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                ticker,
                missing_consensus,
                missing_prices,
                missing_chroma,
                missing_outcomes,
                json.dumps(notes),
            ),
        )
        reports.append({
            "ticker": ticker,
            "missing_consensus": missing_consensus,
            "missing_prices": missing_prices,
            "missing_chroma": missing_chroma,
            "missing_outcomes": missing_outcomes,
            "notes": notes,
        })
    conn.commit()
    conn.close()
    return reports
