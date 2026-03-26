"""Home climate dashboard — fetches temperature and humidity from HA sensors."""

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from phoenix.cache import cache_get
from phoenix.paths import DATA_DIR, star_path, ensure_dirs
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

SENSORS = {
    "Office": "sensor.office_env_temperature",
    "Bedroom": "sensor.bedroom_env_temperature_2",
    "Bathroom": "sensor.bathroom_env_temperature",
    "Server": "sensor.server_closet_temp_temperature",
}

HUMIDITY_SENSORS = {
    "Office": "sensor.office_env_humidity",
    "Bedroom": "sensor.bedroom_env_humidity_2",
    "Bathroom": "sensor.bathroom_env_humidity",
    "Server": "sensor.server_closet_temp_humidity",
}


def _fetch_entity(entity_id: str, settings: Settings) -> dict:
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
    ensure_dirs()

    # Fetch all sensors
    temps = {}
    for name, entity in SENSORS.items():
        data = _fetch_entity(entity, settings)
        state = data.get("state", "—")
        try:
            temps[name] = int(round(float(state)))
        except (ValueError, TypeError):
            temps[name] = state

    humidities = {}
    for name, entity in HUMIDITY_SENSORS.items():
        data = _fetch_entity(entity, settings)
        state = data.get("state", "—")
        try:
            humidities[name] = int(round(float(state)))
        except (ValueError, TypeError):
            humidities[name] = state

    template = star_path("dashboard_panel")

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

    # Render each view separately, then combine into animated webp
    from PIL import Image
    frames = []
    for i, panel_data in enumerate([temp_data, humidity_data]):
        data_file = DATA_DIR / "dashboard_panel_home_climate.json"
        data_file.write_text(json.dumps(panel_data))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_star = shutil.copy(template, tmp)
            tmp_out = Path(tmp) / f"frame_{i}.webp"
            cmd = [
                "pixlet", "render", str(tmp_star),
                "-o", str(tmp_out),
                "-w", str(settings.render_width),
                "-t", str(settings.render_height),
                "instance_id=home_climate",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                logger.error("[home_climate] pixlet failed: %s", proc.stderr)
                raise RuntimeError(f"[home_climate] {proc.stderr.strip().splitlines()[-1]}")
            frames.append(Image.open(tmp_out).convert("RGBA").copy())

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
