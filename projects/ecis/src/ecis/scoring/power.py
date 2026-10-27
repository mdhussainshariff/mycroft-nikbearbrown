"""Power analysis: extra tickers / signals needed for reliable comparisons."""

from __future__ import annotations

import math
from typing import Any


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    if p <= 0:
        return -8.0
    if p >= 1:
        return 8.0
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def n_for_ir(target_ir: float = 0.5, power: float = 0.8, alpha: float = 0.05) -> int:
    """Two-sided z approximation treating IR as a standardized mean."""
    if target_ir <= 0:
        return 0
    z_a = _norm_ppf(1 - alpha / 2)
    z_b = _norm_ppf(power)
    n = ((z_a + z_b) / target_ir) ** 2
    return max(2, math.ceil(n))


def extra_tickers_needed(
    current_n: int,
    target_ir: float = 0.5,
    power: float = 0.8,
    alpha: float = 0.05,
) -> dict[str, Any]:
    needed = n_for_ir(target_ir, power, alpha)
    extra = max(0, needed - current_n)
    return {
        "current_n": current_n,
        "n_required": needed,
        "extra_tickers": extra,
        "target_ir": target_ir,
        "power": power,
        "alpha": alpha,
    }


def n_for_mean_diff(
    delta: float,
    sigma: float,
    power: float = 0.8,
    alpha: float = 0.05,
) -> int:
    """Two-sample n per group to detect a mean difference of `delta`."""
    if delta <= 0 or sigma <= 0:
        return 0
    z_a = _norm_ppf(1 - alpha / 2)
    z_b = _norm_ppf(power)
    n = 2 * ((sigma * (z_a + z_b) / delta) ** 2)
    return max(2, math.ceil(n))


def extra_signals_needed(
    current_n: int,
    sigma: float,
    min_delta: float = 0.02,
    power: float = 0.8,
    alpha: float = 0.05,
    metric: str = "brier",
) -> dict[str, Any]:
    needed = n_for_mean_diff(min_delta, sigma, power, alpha)
    return {
        "metric": metric,
        "current_n": current_n,
        "n_required_per_group": needed,
        "extra_signals": max(0, needed - current_n),
        "min_delta": min_delta,
        "sigma": sigma,
        "power": power,
        "alpha": alpha,
    }
