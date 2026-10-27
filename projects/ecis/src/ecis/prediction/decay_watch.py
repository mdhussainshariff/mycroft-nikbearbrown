"""Watchdog: prediction accuracy vs momentum and rolling calibration decay."""

from __future__ import annotations

from typing import Any

from ecis.prediction.log import fill_actuals, list_predictions
from ecis.prediction.scorecard import score_predictions
from ecis.scoring.drift import check_drift


def _consecutive_below_momentum(rows: list[dict[str, Any]], streak_needed: int = 10) -> int:
    """Count the longest run where the model misses and last-direction momentum hits."""
    streak = 0
    longest = 0
    prior: str | None = None
    for row in rows:
        actual = row.get("actual_direction")
        pred = row.get("predicted_direction")
        if not actual:
            continue
        momentum = prior or "maintained"
        model_hit = pred == actual
        mom_hit = momentum == actual
        if (not model_hit) and mom_hit:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        prior = actual
    return longest


def watch_decay(window: int = 90, streak_needed: int = 10) -> dict[str, Any]:
    fill_actuals()
    graded = [r for r in list_predictions() if r.get("actual_direction")]
    current = score_predictions()
    drift = check_drift()
    alerts: list[str] = []

    mom = next((b for b in current.get("baselines") or [] if b.get("name") == "baseline_momentum"), {})
    models = current.get("models") or []
    for block in models:
        if block.get("n", 0) == 0:
            continue
        if mom.get("accuracy") is not None and block.get("accuracy", 1) < mom["accuracy"]:
            if block.get("n", 0) >= streak_needed:
                alerts.append(f"{block['name']}_below_momentum")
        if isinstance(block.get("ece"), (int, float)) and block["ece"] > 0.12:
            alerts.append(f"{block['name']}_ece_high")
        if isinstance(block.get("skill_score"), (int, float)) and block["skill_score"] < 0.0:
            alerts.append(f"{block['name']}_skill_negative")

    streak = _consecutive_below_momentum(graded, streak_needed)
    if streak >= streak_needed:
        alerts.append("below_momentum_10")

    if drift.get("status") == "alert":
        alerts.append("psi_drift")

    return {
        "window": window,
        "n_graded": len(graded),
        "below_momentum_streak": streak,
        "scorecard": current,
        "drift": drift,
        "alerts": alerts,
        "ok": not alerts,
        "retrain": "below_momentum_10" in alerts,
    }
