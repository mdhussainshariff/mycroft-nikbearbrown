from __future__ import annotations

SECTOR_ETF = {
    "ai": "XLK",
    "technology": "XLK",
    "software": "IGV",
    "semiconductor": "SMH",
    "semiconductors": "SMH",
    "internet": "PNQI",
    "default": "SPY",
}


def sector_etf_for(ticker: str) -> str:
    try:
        from ecis.db.ticker_registry import get_ticker

        row = get_ticker(ticker)
        sector = str((row or {}).get("sector") or "default").lower()
    except Exception:
        sector = "default"
    return SECTOR_ETF.get(sector, SECTOR_ETF["default"])
