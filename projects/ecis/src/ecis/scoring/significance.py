"""Permutation tests for IR, Brier, and pairwise model differences."""

from __future__ import annotations

import math
import random
from typing import Any

from ecis.scoring.metrics import brier_score


def information_ratio(excess: list[float]) -> float:
    if len(excess) < 2:
        return 0.0
    mean = sum(excess) / len(excess)
    var = sum((x - mean) ** 2 for x in excess) / (len(excess) - 1)
    return mean / math.sqrt(var) if var > 0 else 0.0


def permutation_pvalue(
    observed: float,
    null_stats: list[float],
    alternative: str = "greater",
) -> float:
    if not null_stats:
        return 1.0
    if alternative == "greater":
        hits = sum(1 for s in null_stats if s >= observed)
    elif alternative == "less":
        hits = sum(1 for s in null_stats if s <= observed)
    else:
        hits = sum(1 for s in null_stats if abs(s) >= abs(observed))
    return (hits + 1) / (len(null_stats) + 1)


def permute_ir(excess: list[float], n_perm: int = 1000, seed: int = 7) -> dict[str, Any]:
    rng = random.Random(seed)
    obs = information_ratio(excess)
    null = []
    for _ in range(n_perm):
        signs = [rng.choice((-1, 1)) for _ in excess]
        null.append(information_ratio([s * x for s, x in zip(signs, excess)]))
    return {
        "observed_ir": obs,
        "p_value": permutation_pvalue(obs, null, "greater"),
        "n_perm": n_perm,
    }


def permute_brier(
    probs: list[float],
    outcomes: list[int],
    n_perm: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    rng = random.Random(seed)
    obs = brier_score(probs, outcomes)
    y = list(outcomes)
    null = []
    for _ in range(n_perm):
        rng.shuffle(y)
        null.append(brier_score(probs, y))
    return {
        "observed_brier": obs,
        "p_value": permutation_pvalue(obs, null, "less"),
        "n_perm": n_perm,
    }


def paired_permutation_diff(
    metric_a: list[float],
    metric_b: list[float],
    n_perm: int = 10_000,
    seed: int = 7,
) -> dict[str, Any]:
    """Paired permutation test on mean(metric_a - metric_b)."""
    n = min(len(metric_a), len(metric_b))
    if n == 0:
        return {"observed_diff": 0.0, "p_value": 1.0, "n": 0, "n_perm": n_perm}
    diffs = [metric_a[i] - metric_b[i] for i in range(n)]
    observed = sum(diffs) / n
    rng = random.Random(seed)
    null = []
    for _ in range(n_perm):
        flipped = [d if rng.random() < 0.5 else -d for d in diffs]
        null.append(sum(flipped) / n)
    return {
        "observed_diff": observed,
        "p_value": permutation_pvalue(observed, null, "two-sided"),
        "n": n,
        "n_perm": n_perm,
    }


def compare_model_brier(
    groups: dict[str, tuple[list[float], list[int]]],
    n_perm: int = 10_000,
    seed: int = 7,
) -> list[dict[str, Any]]:
    """Pairwise permutation tests on Brier differences between extraction models."""
    names = sorted(groups)
    rows: list[dict[str, Any]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pa, ya = groups[a]
            pb, yb = groups[b]
            if not pa or not pb:
                continue
            ba = brier_score(pa, ya)
            bb = brier_score(pb, yb)
            # unpaired label-shuffle of pooled residuals via paired length truncate
            n = min(len(pa), len(pb))
            residual_a = [(pa[k] - ya[k]) ** 2 for k in range(n)]
            residual_b = [(pb[k] - yb[k]) ** 2 for k in range(n)]
            test = paired_permutation_diff(residual_a, residual_b, n_perm=n_perm, seed=seed)
            rows.append({
                "model_a": a,
                "model_b": b,
                "brier_a": ba,
                "brier_b": bb,
                "diff": ba - bb,
                "p_value": test["p_value"],
                "n": n,
            })
    return rows
