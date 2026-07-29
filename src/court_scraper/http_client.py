"""HTTP fetching with rate limiting, retry/backoff, and a proxy interface.

Two fetchers implement the same :class:`Fetcher` protocol:

* :class:`HttpFetcher` — a real ``requests``-based client (rate limited, retried).
* :class:`FixtureFetcher` — resolves URLs to local fixture files so the whole
  framework runs offline against synthetic data.

Adapters only ever see the :class:`Fetcher` interface, so swapping live fetching
for fixtures (or a Playwright driver) is a one-line change in the CLI.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from court_scraper.logging_config import get_logger

logger = get_logger(__name__)


@runtime_checkable
class Fetcher(Protocol):
    """Anything that can turn a URL into HTML text."""

    def get(self, url: str) -> str: ...


# --------------------------------------------------------------------------- #
# Proxy rotation (pluggable, stubbed)
# --------------------------------------------------------------------------- #
class ProxyProvider(Protocol):
    """Supplies proxy URLs for outbound requests.

    Implement this to plug in a real rotating-proxy pool. The framework calls
    :meth:`next_proxy` before each request and :meth:`report_failure` when a
    request through a proxy fails, so a real implementation can cool down or
    evict bad proxies.
    """

    def next_proxy(self) -> str | None: ...

    def report_failure(self, proxy: str | None) -> None: ...


class StaticProxyProvider:
    """Round-robins over a fixed list of proxies. ``None`` means "direct".

    This is the documented stub referenced in the README; a production build
    would replace it with a pool-backed provider without touching adapters.
    """

    def __init__(self, proxies: list[str] | None = None):
        self._proxies = list(proxies or [])
        self._idx = 0

    def next_proxy(self) -> str | None:
        if not self._proxies:
            return None
        proxy = self._proxies[self._idx % len(self._proxies)]
        self._idx += 1
        return proxy

    def report_failure(self, proxy: str | None) -> None:
        logger.warning("proxy reported failure", extra={"proxy": proxy})


# --------------------------------------------------------------------------- #
# Rate limiter
# --------------------------------------------------------------------------- #
class RateLimiter:
    """Simple token-bucket-ish throttle: at most ``rate`` requests per second."""

    def __init__(self, rate_per_sec: float):
        self._min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last = time.monotonic()


# --------------------------------------------------------------------------- #
# Live HTTP fetcher
# --------------------------------------------------------------------------- #
class HttpFetcher:
    """A polite ``requests`` client: rate limited, retried with backoff.

    Note: ``requests`` is imported lazily so the offline fixture demo (and the
    test suite) never require network libraries to be importable.
    """

    def __init__(
        self,
        rate_per_sec: float = 1.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        timeout: float = 20.0,
        proxy_provider: ProxyProvider | None = None,
        user_agent: str = "texas-court-records-scraper/0.1 (+demo)",
    ):
        self._rate = RateLimiter(rate_per_sec)
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._timeout = timeout
        self._proxies = proxy_provider or StaticProxyProvider()
        self._user_agent = user_agent

    def _backoff(self, attempt: int) -> float:
        # Exponential backoff with full jitter.
        raw = min(self._backoff_cap, self._backoff_base * (2**attempt))
        return random.uniform(0, raw)

    def get(self, url: str) -> str:
        import requests  # lazy import — see class docstring

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._rate.wait()
            proxy = self._proxies.next_proxy()
            proxies = {"http": proxy, "https": proxy} if proxy else None
            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": self._user_agent},
                    proxies=proxies,
                    timeout=self._timeout,
                )
                resp.raise_for_status()
                return resp.text
            except Exception as exc:  # noqa: BLE001 — retry any transport error
                last_exc = exc
                self._proxies.report_failure(proxy)
                delay = self._backoff(attempt)
                logger.warning(
                    "fetch failed; backing off",
                    extra={"url": url, "attempt": attempt, "delay": round(delay, 2)},
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc


# --------------------------------------------------------------------------- #
# Offline fixture fetcher
# --------------------------------------------------------------------------- #
class FixtureFetcher:
    """Resolve URLs to local fixture files for fully offline runs.

    The last path segment of a URL is treated as a filename under
    ``fixtures_dir`` (``.html`` appended if absent). This mirrors how the
    adapters build detail-page URLs from case numbers, so the same adapter code
    exercises real parsing against synthetic pages.
    """

    def __init__(self, fixtures_dir: str | Path):
        self._dir = Path(fixtures_dir)

    def _resolve(self, url: str) -> Path:
        name = Path(urlparse(url).path).name or "index"
        if not name.endswith(".html"):
            name += ".html"
        return self._dir / name

    def get(self, url: str) -> str:
        path = self._resolve(url)
        if not path.exists():
            raise FileNotFoundError(f"no fixture for {url!r} at {path}")
        return path.read_text(encoding="utf-8")
