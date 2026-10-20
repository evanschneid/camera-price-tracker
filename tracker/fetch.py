"""HTTP fetching that looks like a normal browser.

Many shops block plain Python requests. If curl_cffi is installed it
impersonates Chrome's network fingerprint, which gets through far more often;
otherwise we fall back to requests with browser-like headers.
"""
from __future__ import annotations

import random
import time

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

try:  # pragma: no cover - depends on environment
    from curl_cffi import requests as _http
    _IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as _http
    _IMPERSONATE = {}


class FetchError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 25, retries: int = 1) -> str:
    """Return page HTML, retrying once on transient failures."""
    last = None
    for attempt in range(retries + 1):
        try:
            resp = _http.get(url, headers=HEADERS, timeout=timeout, **_IMPERSONATE)
            if resp.status_code == 200:
                return resp.text
            last = f"HTTP {resp.status_code}"
            if resp.status_code in (403, 404, 410):
                break  # retrying won't help
        except Exception as exc:  # network errors vary by backend
            last = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            time.sleep(3 + random.random() * 3)
    raise FetchError(last or "unknown error")


def polite_pause() -> None:
    """Short random gap between requests so we don't hammer anyone."""
    time.sleep(1.5 + random.random() * 2.5)
