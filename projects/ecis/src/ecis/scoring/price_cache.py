"""Local daily price/volume cache (Timescale-style table in SQLite)."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from ecis.db.init_db import get_connection

logger = logging.getLogger(__name__)


def _upsert(ticker: str, day: str, close: float, volume: float | None) -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO market_prices (ticker, price_date, close, volume)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ticker, price_date) DO UPDATE SET
             close = excluded.close, volume = excluded.volume""",
        (ticker.upper(), day, close, volume),
    )
    conn.commit()
    conn.close()


def get_cached(ticker: str, day: str) -> tuple[float, float | None] | None:
    conn = get_connection("agents")
    try:
        row = conn.execute(
            "SELECT close, volume FROM market_prices WHERE ticker = ? AND price_date = ?",
            (ticker.upper(), day),
        ).fetchone()
    except Exception:
        conn.close()
        return None
    conn.close()
    if not row:
        return None
    return float(row["close"]), (float(row["volume"]) if row["volume"] is not None else None)


def fetch_series(ticker: str, start: date, end: date) -> list[tuple[date, float, float | None]]:
    """Return (day, close, volume) from cache, filling gaps via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    try:
        df = yf.download(
            ticker, start=str(start), end=str(end + timedelta(days=1)),
            progress=False, auto_adjust=True,
        )
    except Exception as exc:
        logger.debug("yfinance download failed for %s: %s", ticker, exc)
        return []
    if df is None or getattr(df, "empty", True):
        return []

    rows: list[tuple[date, float, float | None]] = []
    for idx, rec in df.iterrows():
        day = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
        close = rec["Close"]
        if hasattr(close, "iloc"):
            close = close.iloc[0]
        vol = rec["Volume"] if "Volume" in rec else None
        if hasattr(vol, "iloc"):
            vol = vol.iloc[0]
        close_f = float(close)
        vol_f = float(vol) if vol is not None and vol == vol else None
        _upsert(ticker, str(day), close_f, vol_f)
        rows.append((day, close_f, vol_f))
    return rows


def price_on(ticker: str, target: date, tolerance: int = 5) -> float | None:
    cached = get_cached(ticker, str(target))
    if cached:
        return cached[0]
    series = fetch_series(ticker, target - timedelta(days=tolerance), target + timedelta(days=tolerance))
    if not series:
        return None
    nearest = min(series, key=lambda r: abs((r[0] - target).days))
    if abs((nearest[0] - target).days) > tolerance:
        return None
    return nearest[1]


def return_between(ticker: str, start: str, end: str) -> float | None:
    p0 = price_on(ticker, date.fromisoformat(start[:10]))
    p1 = price_on(ticker, date.fromisoformat(end[:10]))
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (p1 - p0) / p0


def trailing_volatility(ticker: str, end: str, window: int = 30) -> float | None:
    end_d = date.fromisoformat(end[:10])
    series = fetch_series(ticker, end_d - timedelta(days=window + 10), end_d)
    closes = [c for d, c, _ in series if d <= end_d][-window:]
    if len(closes) < 5:
        return None
    rets = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) < 4:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


def volume_ratio(ticker: str, around: date, spike_days: int = 5, baseline_days: int = 30) -> float | None:
    series = fetch_series(ticker, around - timedelta(days=baseline_days + 5), around + timedelta(days=spike_days))
    if not series:
        return None
    baseline = [v for d, _, v in series if v and d < around][-baseline_days:]
    window = [v for d, _, v in series if v and around <= d <= around + timedelta(days=spike_days)]
    if not baseline or not window:
        return None
    avg = sum(baseline) / len(baseline)
    if avg <= 0:
        return None
    return (sum(window) / len(window)) / avg
