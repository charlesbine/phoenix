"""Preprocessor for dashboard panel instances.

Each panel is registered as an app named "panel_{id}". This preprocessor
fetches data from the configured HTTP source (through the cache), extracts
values using dot-notation paths, and writes the JSON that dashboard_panel.star reads.
"""

import json
import logging

from phoenix.cache import cache_get
from phoenix.db import PanelDatabase
from phoenix.models import PreprocessorResult
from phoenix.paths import data_path
from phoenix.settings import Settings

logger = logging.getLogger(__name__)


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
                return fmt % v

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


def _fetch_http_source(source: dict) -> dict:
    """Fetch data from an HTTP JSON endpoint through the cache proxy."""
    url = source.get("url", "")
    if not url:
        return {}
    ttl = int(source.get("ttl", 300))
    headers = _build_headers(source)
    status, body, content_type = cache_get(url, ttl, headers=headers if headers else None)
    if status != 200:
        logger.warning("HTTP source returned %d for %s", status, url)
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"_raw": body.decode("utf-8", errors="replace")}


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
    for key in ("color", "label_color", "key_color", "value_color", "title_color"):
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
            items.append({"key": key, "value": str(value) + unit if value is not None else "—"})
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

    return base


def run_panel(panel_id: str, settings: Settings) -> PreprocessorResult:
    """Run preprocessor for a specific panel instance."""
    panel_db = PanelDatabase()
    panel = panel_db.get(panel_id)
    if panel is None:
        return PreprocessorResult(None)

    source = panel.get("data_source", {})
    source_type = source.get("type", "static")

    fetched = {}
    if source_type == "http":
        try:
            fetched = _fetch_http_source(source)
        except Exception:
            logger.warning("[panel:%s] Failed to fetch HTTP source", panel_id)

    panel_data = _build_panel_data(panel, fetched)
    out = data_path(f"dashboard_panel_{panel_id}")
    out.write_text(json.dumps(panel_data))

    return PreprocessorResult(data=panel_data)
