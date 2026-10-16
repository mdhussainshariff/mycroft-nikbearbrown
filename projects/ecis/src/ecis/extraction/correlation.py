"""Pairwise and one-quarter-lagged guidance correlations."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ecis.db.init_db import get_connection, log_agent_action
from ecis.prediction.features import encode_direction


def _series() -> dict[str, dict[str, float]]:
    conn = get_connection("signals")
    rows = conn.execute(
        "SELECT ticker, transcript_date, direction, confidence_raw FROM signals"
    ).fetchall()
    conn.close()
    best: dict[tuple[str, str], tuple[float, str]] = {}
    for row in rows:
        key = (row["ticker"].upper(), str(row["transcript_date"])[:10])
        conf = float(row["confidence_raw"] or 0)
        if key not in best or conf > best[key][0]:
            best[key] = (conf, row["direction"])
    by_ticker: dict[str, dict[str, float]] = defaultdict(dict)
    for (ticker, day), (_, direction) in best.items():
        by_ticker[ticker][day] = encode_direction(direction)
    return by_ticker


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _lagged_pairs(a: dict[str, float], b: dict[str, float], lag: int) -> tuple[list[float], list[float]]:
    days_a = sorted(a)
    days_b = sorted(b)
    xs, ys = [], []
    for i, day in enumerate(days_a):
        j = i + lag
        if lag == 0:
            if day in b:
                xs.append(a[day])
                ys.append(b[day])
            continue
        if j < len(days_b):
            xs.append(a[day])
            ys.append(b[days_b[j]])
    return xs, ys


def update_correlations() -> dict[str, Any]:
    series = _series()
    tickers = sorted(series)
    conn = get_connection("agents")
    n = 0
    high = 0
    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            for lag in (0, 1):
                xs, ys = _lagged_pairs(series[a], series[b], lag)
                coef = _pearson(xs, ys)
                if coef is None:
                    continue
                conn.execute(
                    """INSERT INTO correlations (ticker_a, ticker_b, lag_quarters, coefficient, n_overlap)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(ticker_a, ticker_b, lag_quarters) DO UPDATE SET
                         coefficient = excluded.coefficient,
                         n_overlap = excluded.n_overlap,
                         created_at = datetime('now')""",
                    (a, b, lag, round(coef, 4), len(xs)),
                )
                n += 1
                if abs(coef) >= 0.7:
                    high += 1
    conn.commit()
    conn.close()
    log_agent_action("correlation", f"{n} pairs", "update_matrix", f"high={high}")
    return {"pairs": n, "high_corr": high}


def list_correlations(lag: int = 0) -> list[dict[str, Any]]:
    conn = get_connection("agents")
    try:
        rows = conn.execute(
            "SELECT * FROM correlations WHERE lag_quarters = ? ORDER BY abs(coefficient) DESC",
            (lag,),
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    return [dict(r) for r in rows]


def leading_indicators() -> list[dict[str, Any]]:
    """Tickers whose series at t correlates with peers at t+1 (lag stored as A leads B)."""
    rows = list_correlations(lag=1)
    leaders: dict[str, list[float]] = defaultdict(list)
    laggers: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["coefficient"] is None:
            continue
        leaders[row["ticker_a"]].append(row["coefficient"])
        laggers[row["ticker_b"]].append(row["coefficient"])
    out = []
    for ticker, vals in leaders.items():
        out.append({
            "ticker": ticker,
            "role": "leading",
            "mean_lag_corr": round(sum(vals) / len(vals), 4),
            "n": len(vals),
        })
    for ticker, vals in laggers.items():
        out.append({
            "ticker": ticker,
            "role": "lagging",
            "mean_lag_corr": round(sum(vals) / len(vals), 4),
            "n": len(vals),
        })
    return out
