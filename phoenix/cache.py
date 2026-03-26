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
from contextlib import contextmanager
from typing import Iterator

import httpx

from phoenix.paths import PACKAGE_DIR

logger = logging.getLogger(__name__)

CACHE_DB = PACKAGE_DIR / "cache.db"
DEFAULT_TTL = 300  # 5 minutes

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


def cache_get(url: str, ttl: int = DEFAULT_TTL, headers: dict[str, str] | None = None) -> tuple[int, bytes, str]:
    """Fetch a URL through the cache. Returns (status_code, body, content_type)."""
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
        return row["status_code"], row["body"], row["content_type"]

    # Cache miss or stale — try to fetch fresh
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers or {})
        content_type = resp.headers.get("content-type", "application/octet-stream")
        _store(h, url, resp.status_code, resp.content, content_type, ttl)
        logger.debug("[cache] MISS — fetched fresh %s (%d)", url, resp.status_code)
        return resp.status_code, resp.content, content_type
    except Exception:
        if row:
            logger.warning("[cache] Fetch failed, serving stale for %s", url)
            return row["status_code"], row["body"], row["content_type"]
        logger.error("[cache] Fetch failed, no cache for %s", url)
        raise


def _store(url_hash: str, url: str, status_code: int, body: bytes, content_type: str, ttl: int) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO http_cache
               (url_hash, url, status_code, body, content_type, fetched_at, ttl)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (url_hash, url, status_code, body, content_type, time.time(), ttl),
        )
        conn.commit()
