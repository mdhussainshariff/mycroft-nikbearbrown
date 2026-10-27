"""Per-ticker, per-quarter feature vectors for next-call guidance prediction."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from ecis.db.init_db import get_connection

logger = logging.getLogger(__name__)

DIR_CODE = {"lowered": -1.0, "maintained": 0.0, "raised": 1.0}
TREND_CODE = {
    "single": 0.0,
    "reversal": -1.0,
    "stable_maintained": 0.5,
    "consecutive_lower": -0.75,
    "consecutive_raise": 0.75,
}
FEATURE_NAMES = [
    "prior_direction",
    "prior_confidence",
    "trend",
    "trend_length",
    "days_since_last",
    "stock_return_since_last",
    "sector_pct_raised",
    "precall_momentum",
    "realized_vol_30",
    "consensus_delta",
    "hedging_index",
    "fls_density",
    "tone_shift",
]


def encode_direction(direction: str | None) -> float:
    return DIR_CODE.get((direction or "").lower(), 0.0)


def _parse_day(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _quarter_reps(ticker: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection("signals")
    query = """SELECT signal_id, ticker, direction, confidence_raw, transcript_date,
                      trend, hedging_index, fls_density, tone_shift
               FROM signals"""
    params: list[str] = []
    try:
        if ticker:
            query += " WHERE ticker = ?"
            params.append(ticker.upper())
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    except Exception:
        query = "SELECT signal_id, ticker, direction, confidence_raw, transcript_date FROM signals"
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_key[(str(row["ticker"]).upper(), str(row["transcript_date"])[:10])].append(row)

    reps = []
    for (sym, day), group in by_key.items():
        best = max(group, key=lambda r: float(r.get("confidence_raw") or 0.0))
        reps.append({
            "ticker": sym,
            "transcript_date": day,
            "direction": best["direction"],
            "confidence": float(best.get("confidence_raw") or 0.0),
            "trend": best.get("trend"),
            "hedging_index": best.get("hedging_index"),
            "fls_density": best.get("fls_density"),
            "tone_shift": best.get("tone_shift"),
        })
    reps.sort(key=lambda r: (r["ticker"], r["transcript_date"]))
    return reps


def _trend_length(history: list[dict[str, Any]]) -> int:
    if not history:
        return 0
    last = history[-1]["direction"]
    n = 0
    for row in reversed(history):
        if row["direction"] != last:
            break
        n += 1
    return n


def _sector_mix(reps: list[dict[str, Any]], day: str, exclude: str) -> tuple[float, int]:
    peers = [r for r in reps if r["ticker"] != exclude and r["transcript_date"] == day]
    if len(peers) < 3:
        return 0.0, len(peers)
    raised = sum(1 for r in peers if r["direction"] == "raised")
    return raised / len(peers), len(peers)


def _market_return(ticker: str, start: str, end: str) -> float | None:
    from ecis.scoring.price_cache import return_between

    return return_between(ticker, start, end)


def _realized_vol(ticker: str, end: str, window: int = 30) -> float:
    from ecis.scoring.price_cache import trailing_volatility

    return trailing_volatility(ticker, end, window) or 0.0


def _consensus_delta(ticker: str) -> float:
    from ecis.prediction.consensus import consensus_delta

    return consensus_delta(ticker)


def _zscore_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 3:
        return rows
    import numpy as np

    matrix = np.array([r["vector"] for r in rows], dtype=float)
    mean = np.nanmean(matrix, axis=0)
    std = np.nanstd(matrix, axis=0)
    std[std == 0] = 1.0
    for i, row in enumerate(rows):
        filled = np.nan_to_num(matrix[i], nan=0.0)
        row["vector"] = ((filled - mean) / std).tolist()
        row["features"] = {name: row["vector"][j] for j, name in enumerate(FEATURE_NAMES)}
    return rows


def build_feature_rows(
    ticker: str | None = None,
    *,
    include_next: bool = False,
    normalize: bool = True,
) -> list[dict[str, Any]]:
    """One row per quarter after the first. Target is that quarter's extracted direction.

    Features use only data available before the target date (no leakage).
    Tickers with a single quarter get no training rows; include_next adds a
    forecast row with target=None for the latest history.
    """
    reps = _quarter_reps(ticker)
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reps:
        by_ticker[row["ticker"]].append(row)

    all_reps = _quarter_reps()
    out: list[dict[str, Any]] = []
    for sym, hist in by_ticker.items():
        hist = sorted(hist, key=lambda r: r["transcript_date"])
        if len(hist) < 2 and not include_next:
            continue
        start = 1 if len(hist) >= 2 else 0
        indices = list(range(start, len(hist)))
        if include_next:
            indices.append(len(hist))
        for i in indices:
            prior = hist[:i] if i > 0 else hist[:1]
            if not prior:
                continue
            last = prior[-1]
            target_row = hist[i] if i < len(hist) else None
            as_of = last["transcript_date"]
            target_day = target_row["transcript_date"] if target_row else str(date.today())
            days = (_parse_day(target_day) - _parse_day(as_of)).days
            stock_ret = _market_return(sym, as_of, target_day) or 0.0
            sector_ret = _market_return("XLK", as_of, target_day) or 0.0
            mix, n_peers = _sector_mix(all_reps, as_of, sym)
            low_sector = n_peers < 3
            features = {
                "prior_direction": encode_direction(last["direction"]),
                "prior_confidence": float(last["confidence"]),
                "trend": TREND_CODE.get(str(last.get("trend") or "single"), 0.0),
                "trend_length": float(_trend_length(prior)),
                "days_since_last": float(max(days, 0)),
                "stock_return_since_last": float(stock_ret),
                "sector_pct_raised": 0.0 if low_sector else float(mix),
                "precall_momentum": float(stock_ret - sector_ret),
                "realized_vol_30": float(_realized_vol(sym, as_of)),
                "consensus_delta": float(_consensus_delta(sym)),
                "hedging_index": float(last.get("hedging_index") or 0.0),
                "fls_density": float(last.get("fls_density") or 0.0),
                "tone_shift": float(last.get("tone_shift") or 0.0),
            }
            out.append({
                "ticker": sym,
                "as_of_date": as_of,
                "target_date": target_day if target_row else None,
                "target": target_row["direction"] if target_row else None,
                "features": features,
                "vector": [features[n] for n in FEATURE_NAMES],
                "low_confidence_sector": low_sector,
                "single_quarter": len(hist) < 2,
            })
    if normalize:
        out = _zscore_rows(out)
    return out
