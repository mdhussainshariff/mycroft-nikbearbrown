"""Post-ingest numerical and categorical profiles."""

from __future__ import annotations

import json
import statistics
from typing import Any

from ecis.db.init_db import get_connection


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0, "median": 0, "stdev": 0, "p05": 0, "p95": 0, "iqr_outliers": 0}
    s = sorted(values)
    n = len(s)
    mean = statistics.fmean(s)
    median = statistics.median(s)
    stdev = statistics.pstdev(s) if n > 1 else 0.0
    p05 = s[int(0.05 * (n - 1))]
    p95 = s[int(0.95 * (n - 1))]
    q1 = s[int(0.25 * (n - 1))]
    q3 = s[int(0.75 * (n - 1))]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = sum(1 for v in s if v < lo or v > hi)
    return {
        "mean": round(mean, 6),
        "median": round(median, 6),
        "stdev": round(stdev, 6),
        "p05": round(p05, 6),
        "p95": round(p95, 6),
        "iqr_outliers": outliers,
    }


def profile_data(batch_id: str = "latest") -> list[dict[str, Any]]:
    conn_s = get_connection("signals")
    signals = [dict(r) for r in conn_s.execute("SELECT * FROM signals").fetchall()]
    conn_s.close()
    conn_o = get_connection("outcomes")
    try:
        outcomes = [dict(r) for r in conn_o.execute("SELECT * FROM outcomes").fetchall()]
    except Exception:
        outcomes = []
    conn_o.close()

    numeric: dict[str, list[float]] = {
        "confidence_raw": [float(r["confidence_raw"]) for r in signals if r.get("confidence_raw") is not None],
        "excess_return": [float(r["excess_return"]) for r in outcomes if r.get("excess_return") is not None],
    }
    cats = {
        "direction": {},
        "source_method": {},
    }
    for row in signals:
        cats["direction"][row["direction"]] = cats["direction"].get(row["direction"], 0) + 1
        cats["source_method"][row["source_method"]] = cats["source_method"].get(row["source_method"], 0) + 1

    reports = []
    conn = get_connection("agents")
    for field, values in numeric.items():
        stats = _percentiles(values)
        rec = {
            "field_name": field,
            "field_kind": "numeric",
            "n": len(values),
            "missing": 0,
            **stats,
        }
        conn.execute(
            """INSERT INTO data_profiles
               (batch_id, field_name, field_kind, n, missing, mean, median_val, stdev, p05, p95, iqr_outliers)
               VALUES (?, ?, 'numeric', ?, 0, ?, ?, ?, ?, ?, ?)""",
            (
                batch_id, field, rec["n"], stats["mean"], stats["median"],
                stats["stdev"], stats["p05"], stats["p95"], stats["iqr_outliers"],
            ),
        )
        reports.append(rec)
    for field, freq in cats.items():
        rec = {"field_name": field, "field_kind": "categorical", "n": sum(freq.values()), "freq": freq}
        conn.execute(
            """INSERT INTO data_profiles
               (batch_id, field_name, field_kind, n, missing, extra_json)
               VALUES (?, ?, 'categorical', ?, 0, ?)""",
            (batch_id, field, rec["n"], json.dumps(freq)),
        )
        reports.append(rec)
    conn.commit()
    conn.close()
    return reports
