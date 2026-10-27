"""Wall-clock timing for keyword / FinBERT / NER / LLM readers."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from ecis.db.init_db import get_connection


def log_latency(
    reader_name: str,
    elapsed_ms: float,
    *,
    ticker: str | None = None,
    chunk_index: int | None = None,
    retry_ms: float = 0.0,
) -> None:
    conn = get_connection("agents")
    conn.execute(
        """INSERT INTO extraction_latency
           (ticker, chunk_index, reader_name, elapsed_ms, retry_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (ticker, chunk_index, reader_name, elapsed_ms, retry_ms),
    )
    conn.commit()
    conn.close()


@contextmanager
def timed(reader_name: str, ticker: str | None = None, chunk_index: int | None = None) -> Iterator[dict]:
    box: dict = {"retry_ms": 0.0}
    start = time.perf_counter()
    try:
        yield box
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        try:
            log_latency(
                reader_name, elapsed, ticker=ticker,
                chunk_index=chunk_index, retry_ms=float(box.get("retry_ms") or 0),
            )
        except Exception:
            pass
