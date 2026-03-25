"""Procedural pixel planet — pure Python applet (no Starlark/pixlet)."""

import io
import logging
from pathlib import Path

from PIL import Image

from phoenix.procedural.pixel_planet import PLANET_TYPES, generate_planet_gif
from phoenix.settings import Settings

logger = logging.getLogger(__name__)


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    # Parse hyperparams from config
    planet_type: str | None = config.get("planet_type") or None
    if planet_type and planet_type not in PLANET_TYPES:
        logger.warning("Unknown planet_type '%s', using random", planet_type)
        planet_type = None

    seed: int | None = int(config["seed"]) if config.get("seed") else None

    light_x = float(config.get("light_x", "0.39"))
    light_y = float(config.get("light_y", "0.7"))
    light_origin = (light_x, light_y)

    rotation: float | None = float(config["rotation"]) if config.get("rotation") else None
    time_speed = float(config.get("time_speed", "0.1"))
    n_frames = int(config.get("n_frames", "50"))
    frame_delay = int(config.get("frame_delay", "200"))

    cloud_cover: float | None = float(config["cloud_cover"]) if config.get("cloud_cover") else None
    land_cutoff: float | None = float(config["land_cutoff"]) if config.get("land_cutoff") else None

    # Parse colors: comma-separated hex per layer, pipe-separated layers
    colors: list[list[str]] | None = None
    if config.get("colors"):
        try:
            colors = [
                [f"#{c.strip()}" for c in layer.split(",")]
                for layer in config["colors"].split("|")
            ]
        except Exception:
            logger.warning("Failed to parse colors '%s', using defaults", config["colors"])

    gif_bytes = generate_planet_gif(
        planet_type=planet_type,
        seed=seed,
        size=64,
        n_frames=n_frames,
        frame_delay_ms=frame_delay,
        light_origin=light_origin,
        rotation=rotation,
        time_speed=time_speed,
        cloud_cover=cloud_cover,
        land_cutoff=land_cutoff,
        colors=colors,
    )

    # Write native-size webp
    with Image.open(io.BytesIO(gif_bytes)) as img:
        frames = []
        durations = []
        try:
            while True:
                frames.append(img.copy().convert("RGBA"))
                durations.append(img.info.get("duration", frame_delay))
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        if frames:
            # Native size output
            frames[0].save(
                output, "WEBP", save_all=True, append_images=frames[1:],
                duration=durations, loop=0,
            )

            # Magnified output
            mag = settings.magnification
            large_frames = [
                f.resize((64 * mag, 64 * mag), Image.Resampling.NEAREST)
                for f in frames
            ]
            large_frames[0].save(
                output_large, "WEBP", save_all=True, append_images=large_frames[1:],
                duration=durations, loop=0,
            )
