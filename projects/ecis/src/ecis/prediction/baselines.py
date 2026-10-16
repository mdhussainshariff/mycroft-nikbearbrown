"""Always-maintained and last-quarter momentum baselines."""

from __future__ import annotations

from typing import Any


def always_maintained(rows: list[dict[str, Any]]) -> list[str]:
    return ["maintained"] * len(rows)


def momentum(rows: list[dict[str, Any]]) -> list[str]:
    out = []
    for row in rows:
        prior = row.get("features", {}).get("prior_direction", 0.0)
        if prior > 0.25:
            out.append("raised")
        elif prior < -0.25:
            out.append("lowered")
        else:
            out.append("maintained")
    return out
