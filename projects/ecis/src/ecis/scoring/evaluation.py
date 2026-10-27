"""Phase 14 evaluation: bootstrap CIs, model permutation tests, power."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ecis.config.settings import settings
from ecis.scoring.bootstrap import information_ratio_ci, paired_brier_skill
from ecis.scoring.power import extra_signals_needed, extra_tickers_needed
from ecis.scoring.scorer import _fetch_scored_data
from ecis.scoring.significance import compare_model_brier


def evaluate(
    ticker: str | None = None,
    horizon: int | None = None,
    n_boot: int = 1000,
    n_perm: int = 2000,
) -> dict[str, Any]:
    data = _fetch_scored_data(ticker=ticker)
    if horizon:
        data = [d for d in data if d["horizon_days"] == horizon]
    confs = [d["confidence"] for d in data]
    outs = [int(d["correct"]) for d in data]
    excess = [float(d["excess_return"]) for d in data if d.get("excess_return") is not None]
    ci = paired_brier_skill(confs, outs, n_boot=n_boot) if confs else {}
    ir = information_ratio_ci(excess, n_boot=n_boot) if excess else {}

    groups: dict[str, tuple[list[float], list[int]]] = defaultdict(lambda: ([], []))
    for row in data:
        alias = settings.model_alias(row.get("llm_model") or "") if row.get("llm_model") else "unknown"
        groups[alias][0].append(row["confidence"])
        groups[alias][1].append(int(row["correct"]))
    comparisons = compare_model_brier(dict(groups), n_perm=n_perm)

    residuals = [(c - o) ** 2 for c, o in zip(confs, outs)]
    sigma = 0.0
    if residuals:
        mean = sum(residuals) / len(residuals)
        sigma = (sum((r - mean) ** 2 for r in residuals) / len(residuals)) ** 0.5

    tickers = {d["ticker"] for d in data}
    return {
        "n": len(data),
        "bootstrap": ci,
        "information_ratio": ir,
        "model_comparisons": comparisons,
        "power": {
            "ir": extra_tickers_needed(len(tickers)),
            "brier": extra_signals_needed(len(data), sigma or 0.1),
        },
    }
