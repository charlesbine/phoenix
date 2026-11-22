"""Preprocessor for dashboard panel instances.

Each panel is registered as an app named "panel_{id}". This preprocessor
fetches data from the configured HTTP source (through the cache), extracts
values using dot-notation paths, and writes the JSON that dashboard_panel.star reads.
"""

import json
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from phoenix.cache import cache_get_meta
from phoenix.db import PanelDatabase
from phoenix.models import PreprocessorResult
from phoenix.net import is_valid_ha_entity_id, validate_panel_url
from phoenix.paths import data_path, require_identifier
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

_SAFE_NUMERIC_FMT_RE = re.compile(
    r"^(?:[^%]|%%)*%[-+ #0]?(?:\d{1,2})?(?:\.\d{1,2})?[diuoxXeEfFgG](?:[^%]|%%)*$"
)
_MAX_FMT_LENGTH = 64


@dataclass(frozen=True)
class _SourceFetchResult:
    data: object
    healthy: bool = True
    reason: str = ""
    data_timestamp: float | None = None


def _safe_source_label(url: str) -> str:
    """Return host + path for health messages without leaking credentials or query params."""
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    path = parsed.path or ""
    return f"{host}{path}" if host else "HTTP source"


def _format_duration_short(seconds: float) -> str:
    secs = max(0, int(round(seconds)))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem_mins = mins % 60
    if hours < 24:
        return f"{hours}h {rem_mins}m" if rem_mins else f"{hours}h"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"


def _parse_stale_after(source: dict) -> float | None:
    raw = source.get("stale_after")
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) and val > 0 else None


def _parse_timestamp(value: object) -> float | None:
    """Parse an ISO-8601 timestamp or Unix epoch (seconds or ms) to epoch seconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        if value > 1e12:
            return float(value) / 1000.0
        if value > 1e8:
            return float(value)
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            num = float(text)
        except ValueError:
            pass
        else:
            return _parse_timestamp(num)
        try:
            return datetime.fromisoformat(text).timestamp()
        except ValueError:
            return None
    return None


def _apply_transform(value: object, transform: str) -> object:
    """Apply a simple transform expression to a value.

    Supported:
        / 100          — divide
        * 1000         — multiply
        + 10           — add
        - 5            — subtract
        round 2        — round to N decimal places
        int            — convert to integer
        format $%.2f   — Python format string (value inserted as first arg)

    Chain with |:  "/ 100 | round 2 | format $%.2f"
    """
    if not transform or value is None:
        return value

    try:
        v = float(value)
    except (ValueError, TypeError):
        v = None

    for step in transform.split("|"):
        step = step.strip()
        if not step:
            continue

        if v is not None:
            if step.startswith("/ "):
                v = v / float(step[2:])
            elif step.startswith("* "):
                v = v * float(step[2:])
            elif step.startswith("+ "):
                v = v + float(step[2:])
            elif step.startswith("- "):
                v = v - float(step[2:])
            elif step.startswith("round"):
                places = int(step.split()[1]) if " " in step else 0
                v = round(v, places)
            elif step == "int":
                v = int(v)
            elif step.startswith("format "):
                fmt = step[7:]
                if len(fmt) > _MAX_FMT_LENGTH or _SAFE_NUMERIC_FMT_RE.fullmatch(fmt) is None:
                    logger.warning("Ignoring unsafe panel format specifier: %r", fmt)
                    return str(v)
                try:
                    return fmt % v
                except (TypeError, ValueError, OverflowError):
                    return str(v)

        # String operations (work on any value)
        if step.startswith("prefix "):
            return step[7:] + str(v if v is not None else value)
        elif step.startswith("suffix "):
            return str(v if v is not None else value) + step[7:]

    return v if v is not None else value


def _extract_path(data: object, path: str) -> object:
    """Extract a value from nested dicts/lists using dot notation.

    Examples: "bpi.USD.rate_float", "items.0.name", "temperature"
    """
    current = data
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _build_headers(source: dict) -> dict[str, str]:
    """Build HTTP headers from the auth config."""
    headers: dict[str, str] = {}
    auth = source.get("auth", {})
    auth_type = auth.get("type", "")

    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {auth.get('token', '')}"
    elif auth_type == "api_key":
        header_name = auth.get("header", "X-API-Key")
        headers[header_name] = auth.get("token", "")
    elif auth_type == "basic":
        import base64
        creds = base64.b64encode(f"{auth.get('username', '')}:{auth.get('password', '')}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"

    # Also merge any custom headers
    for k, v in source.get("headers", {}).items():
        headers[k] = v

    return headers


def _fetch_mqtt_source_checked(source: dict) -> _SourceFetchResult:
    """Read the last MQTT message for the configured topic with freshness metadata."""
    from phoenix.mqtt import get_message_with_meta, get_mqtt_client

    topic = str(source.get("topic") or "").strip()
    if not topic:
        return _SourceFetchResult(data={}, healthy=False, reason="MQTT topic not configured")
    try:
        client = get_mqtt_client()
        client.subscribe(topic)
    except Exception:
        pass
    entry = get_message_with_meta(topic)
    if entry is None:
        return _SourceFetchResult(data={}, healthy=False, reason=f"No MQTT message received for '{topic}'")
    msg, received_at = entry
    stale_after = _parse_stale_after(source)
    if stale_after is not None:
        age = max(0.0, time.time() - received_at)
        if age > stale_after:
            return _SourceFetchResult(
                data=msg,
                healthy=False,
                reason=(
                    f"MQTT data stale (last message {_format_duration_short(age)} ago, "
                    f"limit {_format_duration_short(stale_after)})"
                ),
                data_timestamp=received_at,
            )
    return _SourceFetchResult(data=msg, healthy=True, data_timestamp=received_at)


def _fetch_mqtt_source(source: dict) -> dict:
    """Read the last MQTT message for the configured topic."""
    res = _fetch_mqtt_source_checked(source)
    return res.data if isinstance(res.data, dict) else {}


def _fetch_ha_source_checked(source: dict, settings: Settings) -> _SourceFetchResult:
    """Fetch entity state from Home Assistant's REST API with health metadata."""
    entity_id = str(source.get("entity_id") or "").strip()
    if not entity_id:
        return _SourceFetchResult(data={}, healthy=False, reason="Home Assistant entity ID not configured")
    if not is_valid_ha_entity_id(entity_id):
        return _SourceFetchResult(data={}, healthy=False, reason=f"Invalid Home Assistant entity ID '{entity_id}'")
    if not settings.ha_url or not settings.ha_token:
        return _SourceFetchResult(data={}, healthy=False, reason="Home Assistant connection not configured")
    url = f"{settings.ha_url.rstrip('/')}/api/states/{entity_id}"
    ttl = int(source.get("ttl", 60))
    try:
        headers = {"Authorization": f"Bearer {settings.ha_token}"}
        res = cache_get_meta(url, ttl, headers=headers)
    except Exception as exc:
        logger.warning("[ha] Failed to fetch %s", entity_id)
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"Home Assistant fetch failed ({type(exc).__name__}) for '{entity_id}'",
        )
    if res.status_code != 200:
        logger.warning("[ha] %s returned %d", entity_id, res.status_code)
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"Home Assistant returned HTTP {res.status_code} for '{entity_id}'",
        )
    try:
        data = json.loads(res.body)
    except (json.JSONDecodeError, TypeError):
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"Invalid JSON from Home Assistant for '{entity_id}'",
        )
    if not isinstance(data, dict):
        return _SourceFetchResult(data={}, healthy=False, reason=f"Unexpected Home Assistant payload for '{entity_id}'")

    state = data.get("state")
    # Flatten for easy JSONPath access
    result: dict = {
        "state": state,
        "entity_id": data.get("entity_id"),
        "last_updated": data.get("last_updated"),
        "last_changed": data.get("last_changed"),
    }
    attrs = data.get("attributes")
    if isinstance(attrs, dict):
        result.update(attrs)

    if state is None or str(state).strip().lower() in ("", "unavailable", "unknown"):
        label = str(state).strip() if state is not None and str(state).strip() else "empty"
        return _SourceFetchResult(
            data=result,
            healthy=False,
            reason=f"Home Assistant entity '{entity_id}' is {label}",
            data_timestamp=res.fetched_at,
        )

    stale_after = _parse_stale_after(source)
    if res.stale:
        if stale_after is None or res.age_seconds > stale_after:
            return _SourceFetchResult(
                data=result,
                healthy=False,
                reason=f"Home Assistant unreachable (cached {_format_duration_short(res.age_seconds)} ago)",
                data_timestamp=res.fetched_at,
            )
    if stale_after is not None:
        ts = _parse_timestamp(data.get("last_updated")) or res.fetched_at
        age = max(0.0, time.time() - ts)
        if age > stale_after:
            return _SourceFetchResult(
                data=result,
                healthy=False,
                reason=(
                    f"Home Assistant data stale (updated {_format_duration_short(age)} ago, "
                    f"limit {_format_duration_short(stale_after)})"
                ),
                data_timestamp=ts,
            )
    return _SourceFetchResult(data=result, healthy=True, data_timestamp=res.fetched_at)


def _fetch_ha_source(source: dict, settings: Settings) -> dict:
    """Fetch entity state from Home Assistant's REST API."""
    res = _fetch_ha_source_checked(source, settings)
    return res.data if isinstance(res.data, dict) else {}


def _fetch_http_source_checked(source: dict, settings: Settings | None = None) -> _SourceFetchResult:
    """Fetch data from an HTTP JSON endpoint through the cache proxy with health metadata."""
    url = str(source.get("url") or "").strip()
    if not url:
        return _SourceFetchResult(data={}, healthy=False, reason="HTTP source URL not configured")
    label = _safe_source_label(url)
    ttl = int(source.get("ttl", 300))
    headers = _build_headers(source)
    allow_private = bool(settings.allow_private_panel_urls) if settings is not None else False

    def validate(candidate: str) -> None:
        validate_panel_url(candidate, allow_private=allow_private)

    try:
        res = cache_get_meta(url, ttl, headers=headers if headers else None, validate_url=validate)
    except ValueError as exc:
        logger.warning("HTTP source blocked for %s: %s", label, exc)
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"Blocked URL for {label}: {exc}",
        )
    except Exception as exc:
        logger.warning("HTTP source fetch failed for %s: %s", label, type(exc).__name__)
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"HTTP fetch failed ({type(exc).__name__}) for {label}",
        )
    if res.status_code != 200:
        logger.warning("HTTP source returned %d for %s", res.status_code, label)
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"HTTP {res.status_code} from {label}",
        )
    if not res.body or not res.body.strip():
        return _SourceFetchResult(
            data={},
            healthy=False,
            reason=f"Empty response from {label}",
            data_timestamp=res.fetched_at,
        )
    try:
        parsed: object = json.loads(res.body)
    except json.JSONDecodeError:
        parsed = {"_raw": res.body.decode("utf-8", errors="replace")}

    stale_after = _parse_stale_after(source)
    if res.stale:
        if stale_after is not None:
            if res.age_seconds > stale_after:
                return _SourceFetchResult(
                    data=parsed,
                    healthy=False,
                    reason=(
                        f"Data stale (upstream unreachable; cached {_format_duration_short(res.age_seconds)} ago, "
                        f"limit {_format_duration_short(stale_after)})"
                    ),
                    data_timestamp=res.fetched_at,
                )
        else:
            err_tag = res.error or "fetch failed"
            return _SourceFetchResult(
                data=parsed,
                healthy=False,
                reason=f"Upstream unreachable ({err_tag}; cached {_format_duration_short(res.age_seconds)} ago)",
                data_timestamp=res.fetched_at,
            )
    elif stale_after is not None and res.age_seconds > stale_after:
        return _SourceFetchResult(
            data=parsed,
            healthy=False,
            reason=(
                f"Data stale (cached {_format_duration_short(res.age_seconds)} ago, "
                f"limit {_format_duration_short(stale_after)})"
            ),
            data_timestamp=res.fetched_at,
        )

    return _SourceFetchResult(data=parsed, healthy=True, data_timestamp=res.fetched_at)


def _fetch_http_source(source: dict, settings: Settings | None = None, *, raise_on_blocked: bool = False) -> dict:
    """Fetch data from an HTTP JSON endpoint through the cache proxy."""
    if raise_on_blocked:
        url = str(source.get("url") or "").strip()
        allow_private = bool(settings.allow_private_panel_urls) if settings is not None else False
        if url:
            validate_panel_url(url, allow_private=allow_private)
    res = _fetch_http_source_checked(source, settings=settings)
    if raise_on_blocked and not res.healthy and res.reason.startswith("Blocked URL"):
        raise ValueError(res.reason)
    if isinstance(res.data, dict):
        return res.data
    return res.data if isinstance(res.data, list) else {}  # type: ignore[return-value]


def _build_panel_data(panel: dict, fetched: dict) -> dict:
    """Build the JSON data the Starlark template expects."""
    layout = panel["layout"]
    config = panel.get("config", {})
    source = panel.get("data_source", {})
    mappings = source.get("mappings", {})

    base: dict = {
        "layout": layout,
        "title": panel.get("title", ""),
    }

    # Apply color overrides from config
    for key in ("color", "accent_color", "delta_color", "label_color", "key_color", "value_color", "title_color"):
        if config.get(key):
            base[key] = config[key]

    if layout == "big_number":
        value_path = mappings.get("value", "")
        value = _extract_path(fetched, value_path) if value_path else config.get("value", "—")
        transform = mappings.get("transform", "")
        if transform and value is not None:
            value = _apply_transform(value, transform)
        base["value"] = str(value) if value is not None else "—"
        base["unit"] = config.get("unit", "")

        subtitle_path = mappings.get("subtitle", "")
        subtitle = _extract_path(fetched, subtitle_path) if subtitle_path else config.get("subtitle")
        if subtitle is not None and str(subtitle).strip():
            base["subtitle"] = str(subtitle).strip()

        delta_path = mappings.get("delta", "")
        delta = _extract_path(fetched, delta_path) if delta_path else config.get("delta")
        delta_transform = mappings.get("delta_transform", "")
        if delta_transform and delta is not None:
            delta = _apply_transform(delta, delta_transform)
        if delta is not None and str(delta).strip():
            base["delta"] = str(delta).strip()

        progress_path = mappings.get("progress", "")
        progress = _extract_path(fetched, progress_path) if progress_path else config.get("progress")
        if progress is not None and progress != "" and not isinstance(progress, bool):
            try:
                p_val = float(progress)
                if math.isfinite(p_val):
                    base["progress"] = p_val
            except (TypeError, ValueError):
                pass

    elif layout == "key_value":
        items = []
        for item_map in mappings.get("items", []):
            key = item_map.get("key", "")
            value_path = item_map.get("value_path", "")
            value = _extract_path(fetched, value_path) if value_path else item_map.get("value", "")
            transform = item_map.get("transform", "")
            if transform and value is not None:
                value = _apply_transform(value, transform)
            unit = item_map.get("unit", "")
            row: dict = {"key": key, "value": str(value) + unit if value is not None else "—"}
            if item_map.get("color"):
                row["color"] = item_map["color"]
            items.append(row)
        for item in config.get("items", []):
            items.append(item)
        base["items"] = items

    elif layout == "marquee":
        text_path = mappings.get("text", "")
        text = _extract_path(fetched, text_path) if text_path else config.get("text", "")
        transform = mappings.get("transform", "")
        if transform and text is not None:
            text = _apply_transform(text, transform)
        base["text"] = str(text) if text else ""
        if config.get("subtitle"):
            base["subtitle"] = str(config["subtitle"]).strip()

    elif layout == "multi_stat":
        stats = []
        for stat_map in mappings.get("stats", []):
            label = stat_map.get("label", "")
            value_path = stat_map.get("value_path", "")
            value = _extract_path(fetched, value_path) if value_path else stat_map.get("value", "")
            transform = stat_map.get("transform", "")
            if transform and value is not None:
                value = _apply_transform(value, transform)
            unit = stat_map.get("unit", "")
            stat: dict = {"label": label, "value": str(value) + unit if value is not None else "—"}
            if stat_map.get("color"):
                stat["color"] = stat_map["color"]
            stats.append(stat)
        for stat in config.get("stats", []):
            stats.append(stat)
        base["stats"] = stats

    elif layout == "sparkline":
        # Extract array of points
        points_path = mappings.get("points", "")
        points_raw = _extract_path(fetched, points_path) if points_path else config.get("points", [])

        # If points is a list of objects, extract value from each
        value_key = mappings.get("point_value", "")
        if points_raw and isinstance(points_raw, list) and value_key:
            points = []
            for p in points_raw:
                v = _extract_path(p, value_key) if isinstance(p, dict) else p
                transform = mappings.get("point_transform", "")
                if transform and v is not None:
                    v = _apply_transform(v, transform)
                if v is not None:
                    try:
                        points.append(float(v))
                    except (ValueError, TypeError):
                        pass
        elif points_raw and isinstance(points_raw, list):
            points = []
            for v in points_raw:
                try:
                    points.append(float(v))
                except (ValueError, TypeError):
                    pass
        else:
            points = []

        base["points"] = points
        base["fill"] = config.get("fill", True)
        if config.get("unit"):
            base["unit"] = str(config["unit"])
        if config.get("subtitle"):
            base["subtitle"] = str(config["subtitle"]).strip()
        if "show_minmax" in config:
            base["show_minmax"] = bool(config["show_minmax"])

        delta_path = mappings.get("delta", "")
        delta = _extract_path(fetched, delta_path) if delta_path else config.get("delta")
        if delta is not None and str(delta).strip():
            base["delta"] = str(delta).strip()

        # Current value (last point or explicit)
        current_path = mappings.get("value", "")
        current = _extract_path(fetched, current_path) if current_path else config.get("value")
        if current is None and points:
            current = points[-1]
        transform = mappings.get("transform", "")
        if transform and current is not None:
            current = _apply_transform(current, transform)
        if current is not None:
            base["value"] = str(current)

    return base


def _check_payload_freshness(fetched: object, source: dict) -> tuple[bool, str]:
    """Check an optional timestamp field inside the fetched payload against stale_after."""
    timestamp_path = str(source.get("timestamp_path") or "").strip()
    stale_after = _parse_stale_after(source)
    if not timestamp_path or stale_after is None:
        return True, ""
    raw_ts = _extract_path(fetched, timestamp_path)
    ts = _parse_timestamp(raw_ts)
    if ts is None:
        return False, f"Missing or invalid timestamp at '{timestamp_path}'"
    age = max(0.0, time.time() - ts)
    if age > stale_after:
        return (
            False,
            f"Data stale (updated {_format_duration_short(age)} ago, limit {_format_duration_short(stale_after)})",
        )
    return True, ""


def _validate_panel_payload(panel: dict, fetched: object, panel_data: dict) -> tuple[bool, str]:
    """Validate that a dynamic panel received non-empty data for its mapped fields."""
    source = panel.get("data_source", {})
    source_type = source.get("type", "static")
    if source_type == "static":
        return True, ""

    if fetched is None or fetched == {} or fetched == []:
        return False, f"Empty payload from {source_type} source"

    layout = panel["layout"]
    mappings = source.get("mappings") or {}

    if layout == "big_number":
        value_path = str(mappings.get("value") or "").strip()
        if value_path:
            extracted = _extract_path(fetched, value_path)
            if extracted is None or (isinstance(extracted, str) and not extracted.strip()):
                return False, f"Missing value at '{value_path}'"
    elif layout == "key_value":
        mapped_items = [item for item in mappings.get("items", []) if item.get("value_path")]
        if mapped_items and all(_extract_path(fetched, item["value_path"]) is None for item in mapped_items):
            return False, "All mapped fields missing from payload"
    elif layout == "multi_stat":
        mapped_stats = [stat for stat in mappings.get("stats", []) if stat.get("value_path")]
        if mapped_stats and all(_extract_path(fetched, stat["value_path"]) is None for stat in mapped_stats):
            return False, "All mapped stats missing from payload"
    elif layout == "marquee":
        text_path = str(mappings.get("text") or "").strip()
        if text_path:
            extracted = _extract_path(fetched, text_path)
            if extracted is None or not str(extracted).strip():
                return False, f"Missing text at '{text_path}'"
    elif layout == "sparkline":
        points_path = str(mappings.get("points") or "").strip()
        if points_path and not panel_data.get("points"):
            return False, "No data points in payload"

    return True, ""


def run_panel(
    panel_id: str,
    settings: Settings,
    db_path: str | Path | None = None,
) -> PreprocessorResult:
    """Run preprocessor for a specific panel instance."""
    require_identifier(panel_id, "panel id")
    panel_db = PanelDatabase(db_path)
    panel = panel_db.get(panel_id)
    if panel is None:
        return PreprocessorResult(None, healthy=False, health_reason=f"Panel '{panel_id}' not found")

    source = panel.get("data_source", {})
    source_type = source.get("type", "static")

    fetch_result = _SourceFetchResult(data={})
    if source_type == "http":
        fetch_result = _fetch_http_source_checked(source, settings=settings)
    elif source_type == "mqtt":
        fetch_result = _fetch_mqtt_source_checked(source)
    elif source_type == "ha":
        fetch_result = _fetch_ha_source_checked(source, settings)

    fetched = fetch_result.data if fetch_result.data is not None else {}
    panel_data = _build_panel_data(panel, fetched)  # type: ignore[arg-type]
    out = data_path(f"dashboard_panel_{panel_id}")
    out.write_text(json.dumps(panel_data))

    healthy = fetch_result.healthy
    reason = fetch_result.reason
    if healthy and source_type != "static":
        healthy, reason = _validate_panel_payload(panel, fetched, panel_data)
    if healthy and source_type != "static":
        healthy, reason = _check_payload_freshness(fetched, source)

    if not healthy:
        logger.warning("[panel:%s] Data ingress unhealthy: %s", panel_id, reason)

    return PreprocessorResult(data=panel_data, healthy=healthy, health_reason=reason)
