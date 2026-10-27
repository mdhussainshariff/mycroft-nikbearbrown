"""Bootstrap confidence intervals for Brier, skill, IR, and ECE."""

from __future__ import annotations

import math
import random
from typing import Any, Callable

from ecis.scoring.metrics import brier_score, expected_calibration_error, skill_score


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def bootstrap_ci(
    values: list[float],
    stat: Callable[[list[float]], float] | None = None,
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 7,
) -> dict[str, float]:
    if not values:
        return {"estimate": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "n_boot": n_boot}
    fn = stat or _mean
    rng = random.Random(seed)
    n = len(values)
    samples = []
    for _ in range(n_boot):
        draw = [values[rng.randrange(n)] for _ in range(n)]
        samples.append(fn(draw))
    samples.sort()
    return {
        "estimate": fn(values),
        "lo": _percentile(samples, alpha / 2),
        "hi": _percentile(samples, 1 - alpha / 2),
        "n": n,
        "n_boot": n_boot,
    }


def _ece_only(probs: list[float], outcomes: list[int]) -> float:
    ece, _ = expected_calibration_error(probs, outcomes)
    return float(ece)


def paired_brier_skill(
    probs: list[float],
    outcomes: list[int],
    n_boot: int = 1000,
    seed: int = 7,
) -> dict[str, Any]:
    pairs = list(zip(probs, outcomes))
    empty = {"estimate": 0.0, "lo": 0.0, "hi": 0.0}
    if not pairs:
        return {"brier": empty, "skill": empty, "ece": empty}
    rng = random.Random(seed)
    n = len(pairs)
    briers: list[float] = []
    skills: list[float] = []
    eces: list[float] = []
    for _ in range(n_boot):
        draw = [pairs[rng.randrange(n)] for _ in range(n)]
        p, y = [d[0] for d in draw], [d[1] for d in draw]
        b = brier_score(p, y)
        base = sum(y) / len(y)
        ref = base * (1 - base)
        briers.append(b)
        skills.append(skill_score(b, ref))
        eces.append(_ece_only(p, y))
    briers.sort()
    skills.sort()
    eces.sort()
    b_hat = brier_score(probs, outcomes)
    base = sum(outcomes) / len(outcomes)
    skill_hat = skill_score(b_hat, base * (1 - base))
    return {
        "brier": {"estimate": b_hat, "lo": _percentile(briers, 0.025), "hi": _percentile(briers, 0.975)},
        "skill": {"estimate": skill_hat, "lo": _percentile(skills, 0.025), "hi": _percentile(skills, 0.975)},
        "ece": {
            "estimate": _ece_only(probs, outcomes),
            "lo": _percentile(eces, 0.025),
            "hi": _percentile(eces, 0.975),
        },
    }


def information_ratio_ci(excess: list[float], n_boot: int = 1000, seed: int = 7) -> dict[str, float]:
    def ir(xs: list[float]) -> float:
        if len(xs) < 2:
            return 0.0
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
        return mean / math.sqrt(var) if var > 0 else 0.0

    return bootstrap_ci(excess, stat=ir, n_boot=n_boot, seed=seed)
