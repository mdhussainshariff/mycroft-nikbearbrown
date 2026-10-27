from __future__ import annotations

import json
from typing import Any

from ecis.db.init_db import get_connection


def log_prediction(
    ticker: str,
    as_of_date: str,
    direction: str,
    confidence: float,
    features: dict[str, Any],
    model_name: str,
    model_version: str,
) -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT OR IGNORE INTO predictions
           (ticker, as_of_date, predicted_direction, predicted_confidence,
            features_json, model_name, model_version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            ticker.upper(),
            as_of_date,
            direction,
            float(confidence),
            json.dumps(features, default=str),
            model_name,
            model_version,
        ),
    )
    conn.commit()
    conn.close()


def fill_actuals() -> int:
    """Write extracted quarter direction onto predictions that still lack actuals."""
    from ecis.prediction.features import _quarter_reps

    reps = {(r["ticker"], r["transcript_date"]): r["direction"] for r in _quarter_reps()}
    conn = get_connection("agents")
    rows = conn.execute(
        "SELECT prediction_id, ticker, as_of_date FROM predictions WHERE actual_direction IS NULL"
    ).fetchall()
    n = 0
    for row in rows:
        later = [
            (day, d)
            for (sym, day), d in reps.items()
            if sym == row["ticker"] and day > row["as_of_date"]
        ]
        if not later:
            continue
        later.sort()
        conn.execute(
            "UPDATE predictions SET actual_direction = ? WHERE prediction_id = ?",
            (later[0][1], row["prediction_id"]),
        )
        n += 1
    conn.commit()
    conn.close()
    return n


def list_predictions(ticker: str | None = None) -> list[dict[str, Any]]:
    conn = get_connection("agents")
    query = "SELECT * FROM predictions"
    params: list[str] = []
    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())
    query += " ORDER BY as_of_date, ticker"
    rows = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()
    return rows
