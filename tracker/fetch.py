"""HTTP fetching that looks like a normal browser.

Many shops block plain Python requests. If curl_cffi is installed it
impersonates a real browser's network fingerprint and headers, which gets
through far more often. Bot checks score each fingerprint differently, so on
an HTTP 403 we try the next browser profile. Without curl_cffi we fall back to
requests with browser-like headers.
"""
from __future__ import annotations

import random
import time

# Only for the plain-requests fallback. With curl_cffi, the impersonated
# browser sends its own matching headers; adding ours makes the request look
# inconsistent, which is exactly what bot checks look for.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Browser profiles to try, in order, when a shop answers HTTP 403.
PROFILES = ("chrome", "safari", "chrome131")

try:  # pragma: no cover - depends on environment
    from curl_cffi import requests as _http
    _ATTEMPTS = [{"impersonate": p} for p in PROFILES]
except ImportError:  # pragma: no cover
    import requests as _http
    _ATTEMPTS = [{"headers": HEADERS}]


class FetchError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 25, retries: int = 1) -> str:
    """Return page HTML.

    HTTP 403 moves on to the next browser profile; network errors and other
    statuses are retried `retries` times with the same one.
    """
    last = None
    for options in _ATTEMPTS:
        for attempt in range(retries + 1):
            try:
                resp = _http.get(url, timeout=timeout, **options)
                if resp.status_code == 200:
                    return resp.text
                last = f"HTTP {resp.status_code}"
                if resp.status_code in (403, 404, 410):
                    break  # same request won't do better
            except Exception as exc:  # network errors vary by backend
                last = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(3 + random.random() * 3)
        if last != "HTTP 403":
            break  # only a block is worth another browser profile
        time.sleep(1 + random.random() * 2)
    raise FetchError(last or "unknown error")


def polite_pause() -> None:
    """Short random gap between requests so we don't hammer anyone."""
    time.sleep(1.5 + random.random() * 2.5)
