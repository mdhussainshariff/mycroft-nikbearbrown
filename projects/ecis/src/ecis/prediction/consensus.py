from __future__ import annotations

import logging

from ecis.config.settings import settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, float] = {}


def _fmp_json(path: str, params: dict) -> list | dict | None:
    if not settings.fmp_api_key:
        return None
    try:
        import requests

        params = {**params, "apikey": settings.fmp_api_key}
        resp = requests.get(
            f"https://financialmodelingprep.com/api/v3/{path}",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.debug("FMP %s failed: %s", path, exc)
        return None


def consensus_delta(ticker: str) -> float:
    """Signed gap between last extracted guidance and analyst consensus.

    Positive: company last guided above the street. Soft-fails to 0.0.
    """
    key = ticker.upper()
    if key in _CACHE:
        return _CACHE[key]

    delta = 0.0
    data = _fmp_json(f"analyst-estimates/{key}", {"limit": 4})
    if isinstance(data, list) and data:
        row = data[0]
        est = row.get("estimatedEpsAvg") or row.get("estimatedRevenueAvg")
        actual = row.get("epsAvg") or row.get("revenueAvg")
        try:
            if est and actual and float(est) != 0:
                delta = (float(actual) - float(est)) / abs(float(est))
                delta = max(-2.0, min(2.0, delta))
        except (TypeError, ValueError):
            delta = 0.0

    _CACHE[key] = delta
    return delta


def consensus_direction(delta: float, band: float = 0.03) -> str:
    if delta > band:
        return "raised"
    if delta < -band:
        return "lowered"
    return "maintained"
