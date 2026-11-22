"""Home climate dashboard — fetches temperature and humidity from HA sensors."""

import json
import logging
from pathlib import Path

from phoenix.cache import cache_get
from phoenix.models import DataIngressError
from phoenix.net import is_valid_ha_entity_id
from phoenix.panel_render import render_panel_frames
from phoenix.paths import ensure_dirs
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_SENSORS = {
    "Living": "sensor.living_room_temperature",
    "Bedroom": "sensor.bedroom_temperature",
    "Office": "sensor.office_temperature",
    "Kitchen": "sensor.kitchen_temperature",
}

DEFAULT_HUMIDITY_SENSORS = {
    "Living": "sensor.living_room_humidity",
    "Bedroom": "sensor.bedroom_humidity",
    "Office": "sensor.office_humidity",
    "Kitchen": "sensor.kitchen_humidity",
}

SETTINGS_SCHEMA = [
    {
        "id": "temperature_sensors",
        "name": "Temperature Sensors",
        "desc": "Comma-separated Label=entity_id pairs (e.g. Living=sensor.living_room_temperature, Office=sensor.office_temperature).",
        "type": "text",
        "default": ", ".join(f"{k}={v}" for k, v in DEFAULT_SENSORS.items()),
    },
    {
        "id": "humidity_sensors",
        "name": "Humidity Sensors",
        "desc": "Comma-separated Label=entity_id pairs (e.g. Living=sensor.living_room_humidity, Office=sensor.office_humidity).",
        "type": "text",
        "default": ", ".join(f"{k}={v}" for k, v in DEFAULT_HUMIDITY_SENSORS.items()),
    },
]


def _parse_sensor_map(raw: str | None, fallback: dict[str, str]) -> dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return dict(fallback)
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {str(k).strip(): str(v).strip() for k, v in parsed.items() if str(k).strip() and str(v).strip()}
        except json.JSONDecodeError:
            pass
    sensors: dict[str, str] = {}
    for entry in text.split(","):
        if "=" in entry:
            label, entity_id = entry.split("=", 1)
            label, entity_id = label.strip(), entity_id.strip()
            if label and entity_id:
                sensors[label] = entity_id
    return sensors or dict(fallback)


def _fetch_entity(entity_id: str, settings: Settings) -> dict:
    if not is_valid_ha_entity_id(entity_id):
        logger.warning("[home_climate] Ignoring invalid Home Assistant entity_id: %r", entity_id)
        return {}
    url = f"{settings.ha_url.rstrip('/')}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    try:
        status, body, _ = cache_get(url, ttl=60, headers=headers)
        if status == 200:
            return json.loads(body)
    except Exception:
        pass
    return {}


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    if not settings.ha_url or not settings.ha_token:
        raise ValueError("Home climate needs a configured Home Assistant connection")
    ensure_dirs()

    temp_sensors = _parse_sensor_map(config.get("temperature_sensors"), DEFAULT_SENSORS)
    humidity_sensors = _parse_sensor_map(config.get("humidity_sensors"), DEFAULT_HUMIDITY_SENSORS)

    # Fetch all sensors
    valid_readings = 0
    temps = {}
    for name, entity in temp_sensors.items():
        data = _fetch_entity(entity, settings)
        state = data.get("state", "—")
        try:
            temps[name] = int(round(float(state)))
            valid_readings += 1
        except (ValueError, TypeError):
            temps[name] = state

    humidities = {}
    for name, entity in humidity_sensors.items():
        data = _fetch_entity(entity, settings)
        state = data.get("state", "—")
        try:
            humidities[name] = int(round(float(state)))
            valid_readings += 1
        except (ValueError, TypeError):
            humidities[name] = state

    if valid_readings == 0:
        raise DataIngressError("All Home Assistant climate sensors unavailable")

    # Render both views as separate frames into an animated webp
    temp_data = {
        "layout": "multi_stat",
        "title": "Temperature",
        "stats": [
            {"label": name, "value": f"{val}°", "color": _temp_color(val)}
            for name, val in temps.items()
        ],
    }
    humidity_data = {
        "layout": "multi_stat",
        "title": "Humidity",
        "stats": [
            {"label": name, "value": f"{val}%", "color": _humidity_color(val)}
            for name, val in humidities.items()
        ],
    }

    from PIL import Image
    frames = []
    for panel_data in (temp_data, humidity_data):
        rendered, _ = render_panel_frames(
            panel_data,
            width=settings.render_width,
            height=settings.render_height,
        )
        if rendered:
            frames.append(rendered[0].convert("RGBA"))

    if not frames:
        return

    # Save as animated webp — 5 seconds per frame
    frame_duration = 5000
    frames[0].save(
        output, "WEBP", save_all=True, append_images=frames[1:],
        duration=[frame_duration] * len(frames), loop=0,
    )

    # Magnified version
    mag = settings.magnification
    large_frames = [
        f.resize((settings.render_width * mag, settings.render_height * mag), Image.Resampling.NEAREST)
        for f in frames
    ]
    large_frames[0].save(
        output_large, "WEBP", save_all=True, append_images=large_frames[1:],
        duration=[frame_duration] * len(large_frames), loop=0,
    )

def _temp_color(val: object) -> str:
    """Color based on temperature."""
    try:
        t = float(val)
    except (ValueError, TypeError):
        return "#FFFFFF"
    if t < 20:
        return "#5BCEFA"  # cold blue
    elif t < 24:
        return "#00FF88"  # comfortable green
    elif t < 27:
        return "#FF8C00"  # warm orange
    else:
        return "#FF4444"  # hot red


def _humidity_color(val: object) -> str:
    """Color based on humidity."""
    try:
        h = float(val)
    except (ValueError, TypeError):
        return "#FFFFFF"
    if h < 30:
        return "#FF8C00"  # too dry
    elif h < 50:
        return "#00FF88"  # comfortable
    elif h < 60:
        return "#5BCEFA"  # getting humid
    else:
        return "#FF4444"  # too humid
