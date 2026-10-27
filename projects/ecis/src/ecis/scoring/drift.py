"""Population Stability Index and KL drift between prediction / feature windows."""

from __future__ import annotations

import math
from typing import Any

from ecis.db.init_db import get_connection

EPS = 1e-12


def psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi <= lo:
        return 0.0
    width = (hi - lo) / bins
    e_counts = [0] * bins
    a_counts = [0] * bins
    for v in expected:
        e_counts[min(bins - 1, int((v - lo) / width))] += 1
    for v in actual:
        a_counts[min(bins - 1, int((v - lo) / width))] += 1
    n_e, n_a = len(expected), len(actual)
    score = 0.0
    for e, a in zip(e_counts, a_counts):
        pe = max(e / n_e, EPS)
        pa = max(a / n_a, EPS)
        score += (pa - pe) * math.log(pa / pe)
    return score


def kl_divergence(expected: list[float], actual: list[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    lo = min(min(expected), min(actual))
    hi = max(max(expected), max(actual))
    if hi <= lo:
        return 0.0
    width = (hi - lo) / bins
    e_counts = [EPS] * bins
    a_counts = [EPS] * bins
    for v in expected:
        e_counts[min(bins - 1, int((v - lo) / width))] += 1
    for v in actual:
        a_counts[min(bins - 1, int((v - lo) / width))] += 1
    n_e, n_a = sum(e_counts), sum(a_counts)
    return sum((a / n_a) * math.log((a / n_a) / (e / n_e)) for e, a in zip(e_counts, a_counts))


def _split_series(values: list[float], split: float) -> tuple[list[float], list[float]]:
    cut = max(2, int(len(values) * split))
    return values[:cut], values[cut:]


def _prediction_probs() -> list[float]:
    conn = get_connection("agents")
    try:
        rows = conn.execute(
            "SELECT predicted_confidence FROM predictions ORDER BY as_of_date, prediction_id"
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [float(r["predicted_confidence"]) for r in rows if r["predicted_confidence"] is not None]


def _signal_feature(column: str) -> list[float]:
    conn = get_connection("signals")
    try:
        rows = conn.execute(
            f"SELECT {column} FROM signals WHERE {column} IS NOT NULL ORDER BY transcript_date"
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [float(r[column]) for r in rows]


def _log_alert(feature: str, metric: str, value: float, window_a: str, window_b: str) -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO drift_alerts (feature, metric, value, window_a, window_b)
           VALUES (?, ?, ?, ?, ?)""",
        (feature, metric, value, window_a, window_b),
    )
    conn.commit()
    conn.close()


def check_drift(split: float = 0.5, psi_alert: float = 0.2) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    series = {
        "prediction_prob": _prediction_probs(),
        "confidence_raw": _signal_feature("confidence_raw"),
        "hedging_index": _signal_feature("hedging_index"),
    }
    for name, values in series.items():
        if len(values) < 8:
            reports.append({"feature": name, "status": "insufficient", "n": len(values)})
            continue
        expected, actual = _split_series(values, split)
        psi_v = psi(expected, actual)
        kl_v = kl_divergence(expected, actual)
        status = "alert" if psi_v >= psi_alert else "ok"
        _log_alert(name, "psi", psi_v, f"n={len(expected)}", f"n={len(actual)}")
        _log_alert(name, "kl", kl_v, f"n={len(expected)}", f"n={len(actual)}")
        reports.append({
            "feature": name,
            "status": status,
            "psi": round(psi_v, 6),
            "kl": round(kl_v, 6),
            "n_expected": len(expected),
            "n_actual": len(actual),
        })
    alerted = [r for r in reports if r.get("status") == "alert"]
    return {
        "status": "alert" if alerted else "ok",
        "features": reports,
    }
