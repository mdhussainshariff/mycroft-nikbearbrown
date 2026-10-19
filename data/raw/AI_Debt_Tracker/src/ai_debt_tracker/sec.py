"""The one door to sec.gov: a declared User-Agent, a shared rate limit, retries, an on-disk cache.

P2 says only ingest code touches the network; everything that talks to the SEC goes through
`SecClient`, so the fair-access rule (P14: at most 10 requests per second, contact in the
User-Agent) is enforced in one place. The limiter is per process and set to 8 per second to leave
headroom; scripts that run several processes at once must divide it.
"""

from __future__ import annotations

import hashlib
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config


class RateLimiter:
    """At most `rate` acquisitions per second, shared by every thread in the process."""

    def __init__(self, rate: float = 8.0, clock=time.monotonic, sleep=time.sleep):
        self.interval = 1.0 / rate
        self._next = 0.0
        self._lock = threading.Lock()
        self._clock, self._sleep = clock, sleep

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            self._sleep(wait)


_LIMITER = RateLimiter(8.0)


class SecClient:
    def __init__(self, cache_dir: Path | None = None, limiter: RateLimiter | None = None, user_agent: str | None = None):
        self.cache_dir = cache_dir or config.data_dir() / "edgar_cache"
        self.limiter = limiter or _LIMITER
        self._ua = user_agent

    @property
    def ua(self) -> str:
        if self._ua is None:
            self._ua = config.user_agent()
        return self._ua

    def cache_path(self, url: str) -> Path:
        tail = url.split("://", 1)[-1]
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in tail)[-120:]
        return self.cache_dir / hashlib.sha256(url.encode()).hexdigest()[:2] / safe

    def get(self, url: str, *, cache: bool = True, retries: int = 3, timeout: int = 300) -> bytes:
        """GET with the cache in front. `cache=False` is for documents that change (the
        submissions index); filed documents never change once accepted, so they are cached."""
        path = self.cache_path(url)
        if cache and path.exists():
            return path.read_bytes()
        for attempt in range(retries):
            self.limiter.acquire()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                break
            except urllib.error.HTTPError as ex:
                if ex.code == 404 or attempt == retries - 1:
                    raise
                time.sleep(2 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError):
                if attempt == retries - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        if cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(body)
            tmp.replace(path)
        return body

    def download(self, url: str, dest: Path) -> Path:
        """Large files (the monthly notes zips) go to a named path instead of the URL cache."""
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(self.get(url, cache=False, timeout=900))
        tmp.replace(dest)
        return dest
