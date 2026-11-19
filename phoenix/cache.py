"""HTTP caching layer — sits between applets and external APIs.

Starlark apps hit: http://localhost:{dashboard_port}/proxy?url={encoded_url}&ttl={seconds}
Preprocessors use: cache_get(url, ttl=300) directly from Python.

On cache hit (fresh): returns cached response immediately.
On cache miss or stale: fetches fresh, caches it, returns it.
On fetch failure + stale cache: returns stale data (better than crashing).
On fetch failure + no cache: raises.
"""

import hashlib
import logging
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urljoin

import httpx

from phoenix.paths import PACKAGE_DIR

logger = logging.getLogger(__name__)

CACHE_DB = PACKAGE_DIR / "cache.db"
DEFAULT_TTL = 300  # 5 minutes
MAX_REDIRECTS = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    url_hash TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    body BLOB NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    fetched_at REAL NOT NULL,
    ttl REAL NOT NULL
);
"""

_initialized = False


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    global _initialized
    conn = sqlite3.connect(str(CACHE_DB), timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.row_factory = sqlite3.Row
        if not _initialized:
            conn.executescript(_SCHEMA)
            _initialized = True
        yield conn
    finally:
        conn.close()


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _fetch_with_validation(
    url: str,
    headers: dict[str, str],
    validate_url: Callable[[str], None],
) -> httpx.Response:
    """Follow redirects manually so every hop is re-validated against SSRF rules."""
    current = url
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current)
            resp = client.get(current, headers=headers)
            if resp.is_redirect and resp.headers.get("location"):
                current = urljoin(current, resp.headers["location"])
                continue
            return resp
    raise ValueError("Too many redirects")


@dataclass(frozen=True)
class CacheResponse:
    status_code: int
    body: bytes
    content_type: str
    fetched_at: float
    from_cache: bool = False
    stale: bool = False
    error: str | None = None

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.fetched_at)


def cache_get_meta(
    url: str,
    ttl: int = DEFAULT_TTL,
    headers: dict[str, str] | None = None,
    *,
    validate_url: Callable[[str], None] | None = None,
) -> CacheResponse:
    """Fetch a URL through the cache with freshness and fallback metadata."""
    if validate_url is not None:
        validate_url(url)

    now = time.time()
    # Include headers in cache key so different auth tokens get separate cache entries
    h = _url_hash(url + (str(sorted(headers.items())) if headers else ""))

    # Check cache
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM http_cache WHERE url_hash = ?", (h,)
        ).fetchone()

    if row and (now - row["fetched_at"]) < row["ttl"]:
        logger.debug("[cache] HIT (fresh) %s", url)
        return CacheResponse(
            status_code=row["status_code"],
            body=row["body"],
            content_type=row["content_type"],
            fetched_at=row["fetched_at"],
            from_cache=True,
            stale=False,
        )

    # Cache miss or stale — try to fetch fresh
    try:
        if validate_url is not None:
            resp = _fetch_with_validation(url, headers or {}, validate_url)
        else:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(url, headers=headers or {})
        content_type = resp.headers.get("content-type", "application/octet-stream")
        fetched_at = time.time()
        if 200 <= resp.status_code < 300:
            _store(h, url, resp.status_code, resp.content, content_type, ttl, fetched_at)
        logger.debug("[cache] MISS — fetched fresh %s (%d)", url, resp.status_code)
        return CacheResponse(
            status_code=resp.status_code,
            body=resp.content,
            content_type=content_type,
            fetched_at=fetched_at,
            from_cache=False,
            stale=False,
        )
    except ValueError:
        raise
    except Exception as exc:
        if row:
            logger.warning("[cache] Fetch failed, serving stale for %s", url)
            return CacheResponse(
                status_code=row["status_code"],
                body=row["body"],
                content_type=row["content_type"],
                fetched_at=row["fetched_at"],
                from_cache=True,
                stale=True,
                error=type(exc).__name__,
            )
        logger.error("[cache] Fetch failed, no cache for %s", url)
        raise


def cache_get(
    url: str,
    ttl: int = DEFAULT_TTL,
    headers: dict[str, str] | None = None,
    *,
    validate_url: Callable[[str], None] | None = None,
) -> tuple[int, bytes, str]:
    """Fetch a URL through the cache. Returns (status_code, body, content_type)."""
    res = cache_get_meta(url, ttl, headers=headers, validate_url=validate_url)
    return res.status_code, res.body, res.content_type


def _store(
    url_hash: str,
    url: str,
    status_code: int,
    body: bytes,
    content_type: str,
    ttl: int,
    fetched_at: float | None = None,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO http_cache
               (url_hash, url, status_code, body, content_type, fetched_at, ttl)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (url_hash, url, status_code, body, content_type, fetched_at or time.time(), ttl),
        )
        conn.commit()
