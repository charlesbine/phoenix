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

from phoenix.paths import DB_PATH

logger = logging.getLogger(__name__)

CACHE_DB = DB_PATH.parent / "cache.db"
DEFAULT_TTL = 300  # 5 minutes
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB


class ResponseTooLargeError(ValueError):
    """Raised when an upstream HTTP response exceeds MAX_RESPONSE_BYTES."""

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


def _read_bounded_response(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    max_bytes: int,
) -> tuple[int, bytes, dict[str, str], bool]:
    """Fetch a single HTTP response while enforcing a streaming max body size cap."""
    if hasattr(client, "stream"):
        with client.stream("GET", url, headers=headers) as resp:
            if resp.is_redirect and resp.headers.get("location"):
                return resp.status_code, b"", dict(resp.headers), True
            raw_len = resp.headers.get("content-length")
            if raw_len is not None:
                try:
                    declared = int(raw_len)
                except ValueError:
                    declared = None
                if declared is not None and declared > max_bytes:
                    raise ResponseTooLargeError(f"Upstream response exceeds {max_bytes} byte limit")
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ResponseTooLargeError(f"Upstream response exceeds {max_bytes} byte limit")
                chunks.append(chunk)
            return resp.status_code, b"".join(chunks), dict(resp.headers), False

    # Fallback for test doubles that only implement client.get()
    resp = client.get(url, headers=headers)
    if resp.is_redirect and resp.headers.get("location"):
        return resp.status_code, b"", dict(resp.headers), True
    body = resp.content
    if len(body) > max_bytes:
        raise ResponseTooLargeError(f"Upstream response exceeds {max_bytes} byte limit")
    return resp.status_code, body, dict(resp.headers), False


def _header_get(headers: dict[str, str], key: str, default: str = "") -> str:
    key_lower = key.lower()
    for k, v in headers.items():
        if k.lower() == key_lower:
            return v
    return default


def _fetch_with_validation(
    url: str,
    headers: dict[str, str],
    validate_url: Callable[[str], None],
    max_bytes: int,
) -> tuple[int, bytes, dict[str, str]]:
    """Follow redirects manually so every hop is re-validated against SSRF rules."""
    current = url
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current)
            status_code, body, resp_headers, is_redirect = _read_bounded_response(
                client, current, headers, max_bytes
            )
            if is_redirect:
                location = _header_get(resp_headers, "location")
                if location:
                    current = urljoin(current, location)
                    continue
            return status_code, body, resp_headers
    raise ValueError("Too many redirects")


def _fetch_unvalidated(
    url: str,
    headers: dict[str, str],
    max_bytes: int,
) -> tuple[int, bytes, dict[str, str]]:
    """Fetch a URL with redirects and streaming body size enforcement."""
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        status_code, body, resp_headers, _ = _read_bounded_response(client, url, headers, max_bytes)
        return status_code, body, resp_headers


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
    max_bytes: int | None = None,
) -> CacheResponse:
    """Fetch a URL through the cache with freshness and fallback metadata."""
    if validate_url is not None:
        validate_url(url)

    limit = MAX_RESPONSE_BYTES if max_bytes is None else max_bytes
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
            status_code, body, resp_headers = _fetch_with_validation(url, headers or {}, validate_url, limit)
        else:
            status_code, body, resp_headers = _fetch_unvalidated(url, headers or {}, limit)
        content_type = _header_get(resp_headers, "content-type", "application/octet-stream")
        fetched_at = time.time()
        if 200 <= status_code < 300:
            _store(h, url, status_code, body, content_type, ttl, fetched_at)
        logger.debug("[cache] MISS — fetched fresh %s (%d)", url, status_code)
        return CacheResponse(
            status_code=status_code,
            body=body,
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
    max_bytes: int | None = None,
) -> tuple[int, bytes, str]:
    """Fetch a URL through the cache. Returns (status_code, body, content_type)."""
    res = cache_get_meta(url, ttl, headers=headers, validate_url=validate_url, max_bytes=max_bytes)
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
