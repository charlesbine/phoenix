"""Package deliveries via MQTT. Only renders when packages are pending."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from phoenix.mqtt import get_message, get_mqtt_client
from phoenix.panel_render import render_panel_to_files
from phoenix.paths import ensure_dirs
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_STATE_TOPIC = "home/deliveries/state"
DEFAULT_ATTRIBUTES_TOPIC = "home/deliveries/attributes"

SETTINGS_SCHEMA = [
    {
        "id": "state_topic",
        "name": "State MQTT Topic",
        "desc": "MQTT topic publishing the pending package count (integer payload).",
        "type": "text",
        "default": DEFAULT_STATE_TOPIC,
    },
    {
        "id": "attributes_topic",
        "name": "Attributes MQTT Topic",
        "desc": "MQTT topic publishing JSON delivery details with a 'deliveries' list.",
        "type": "text",
        "default": DEFAULT_ATTRIBUTES_TOPIC,
    },
]


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    ensure_dirs()

    state_topic = (config.get("state_topic") or "").strip() or DEFAULT_STATE_TOPIC
    attributes_topic = (config.get("attributes_topic") or "").strip() or DEFAULT_ATTRIBUTES_TOPIC

    # Ensure we're subscribed to the topics
    try:
        client = get_mqtt_client(settings)
        client.subscribe(state_topic)
        client.subscribe(attributes_topic)
    except Exception:
        pass

    # Read last state
    state_msg = get_message(state_topic)
    count = 0
    if state_msg:
        try:
            count = int(state_msg.get("_raw", "0"))
        except (ValueError, TypeError):
            count = 0

    if count == 0:
        # No packages — signal to skip this app
        # Remove output files so display manager skips it
        for f in [output, output_large]:
            if f.exists():
                f.unlink()
        return

    # Read delivery details
    attrs = get_message(attributes_topic)
    deliveries = []
    if attrs and isinstance(attrs, dict):
        deliveries = attrs.get("deliveries", [])

    # Build display data
    if len(deliveries) <= 4:
        # Multi-stat: show each package type
        panel_data = {
            "layout": "multi_stat",
            "title": f"{count} Package{'s' if count != 1 else ''}",
            "stats": [],
        }
        for d in deliveries[:4]:
            pkg_type = d.get("type", "Package")
            # Shorten common types
            short = pkg_type.replace("Delivery", "").replace("Package", "Pkg").strip()
            received = d.get("received_utc", "")
            age = _format_age(received)
            panel_data["stats"].append({
                "label": age,
                "value": short[:8],
                "color": "#FFD700",
            })
    else:
        # Key/value list for many packages
        panel_data = {
            "layout": "key_value",
            "title": f"{count} Packages",
            "key_color": "#FFD700",
            "items": [],
        }
        for d in deliveries[:5]:
            pkg_type = d.get("type", "Package").replace("Delivery", "").replace("Package", "Pkg").strip()
            age = _format_age(d.get("received_utc", ""))
            panel_data["items"].append({"key": pkg_type[:10] + ":", "value": age})

    # Render directly with the pure-Python panel renderer
    render_panel_to_files(
        panel_data,
        output,
        output_large,
        width=settings.render_width,
        height=settings.render_height,
        magnification=settings.magnification,
    )


def _format_age(iso_time: str) -> str:
    """Format an ISO timestamp as a relative age string."""
    if not iso_time:
        return "?"
    try:
        received = datetime.fromisoformat(iso_time)
        now = datetime.now(timezone.utc)
        delta = now - received
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        elif hours < 24:
            return f"{int(hours)}h ago"
        else:
            return f"{int(hours / 24)}d ago"
    except Exception:
        return "?"
