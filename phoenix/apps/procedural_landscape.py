"""A continuous flight over a seeded, wrapping pixel landscape."""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from phoenix.procedural.pixel_planet import _fbm
from phoenix.settings import Settings

PALETTES = {
    "dusk": {
        "sky": ("#211e43", "#b66780"),
        "sun": "#ffc685",
        "water": "#555d91",
        "shore": "#d5989e",
        "land": ("#33354f", "#586178", "#889e9d", "#d5b9b5"),
    },
    "alpine": {
        "sky": ("#1b3454", "#91b5bb"),
        "sun": "#ffe4b5",
        "water": "#387591",
        "shore": "#c1bd91",
        "land": ("#243b48", "#48645a", "#91a68b", "#e5ded0"),
    },
    "alien": {
        "sky": ("#221738", "#986082"),
        "sun": "#ffc1b5",
        "water": "#54446e",
        "shore": "#da9eae",
        "land": ("#34304d", "#676083", "#a3a3a6", "#e3c7b9"),
    },
}
SETTINGS_SCHEMA = [
    {
        "type": "dropdown",
        "id": "palette",
        "name": "Landscape",
        "default": "dusk",
        "options": [{"value": key, "display": key.title()} for key in PALETTES],
    },
    {
        "type": "number",
        "id": "seed",
        "name": "Seed",
        "desc": "Leave empty for a new landscape.",
    },
]
MAP_SIZE = 128
FRAME_COUNT = 240
FRAME_DELAY_MS = 50


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(hex_color.lstrip("#")))


def _blend(first: tuple, second: tuple, amount: float) -> tuple[int, int, int]:
    return tuple(round(a + (b - a) * amount) for a, b in zip(first, second))


def _terrain(seed: int, palette: dict) -> tuple[list, list]:
    """Build a toroidal height and color map with a meandering sea channel."""
    heights, colors = [], []
    for z in range(MAP_SIZE):
        row, color_row = [], []
        channel = (
            64
            + 14 * math.sin(math.tau * z / MAP_SIZE)
            + 5 * math.sin(2 * math.tau * z / MAP_SIZE)
        )
        for x in range(MAP_SIZE):
            noise = _fbm(x * 10 / MAP_SIZE, z * 10 / MAP_SIZE, seed, octaves=4)
            ridge = abs(noise - 0.46) * 2.8
            distance = abs((x - channel + MAP_SIZE / 2) % MAP_SIZE - MAP_SIZE / 2)
            valley = min(1, max(0, (distance - 5) / 18))
            height = 2 + (5 + ridge * 22) * valley
            if height <= 2.4:
                color = _rgb(palette["water"])
            elif height < 4:
                color = _rgb(palette["shore"])
            else:
                color = _rgb(palette["land"][min(3, int((height - 4) / 5))])
            row.append(height)
            color_row.append(color)
        heights.append(row)
        colors.append(color_row)
    for z in range(MAP_SIZE):
        for x in range(MAP_SIZE):
            if heights[z][x] > 4:
                slope = heights[z][(x + 1) % MAP_SIZE] - heights[z][(x - 1) % MAP_SIZE]
                light = max(-0.24, min(0.24, -slope * 0.07))
                target = (250, 224, 200) if light > 0 else (16, 19, 40)
                colors[z][x] = _blend(colors[z][x], target, abs(light))
    return heights, colors


def _frame(heights: list, colors: list, palette: dict, phase: float) -> Image.Image:
    """Draw depth slices from the camera to the horizon, hiding occluded pixels."""
    phase %= 1
    image = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(image)
    sky_top, sky_bottom = map(_rgb, palette["sky"])
    for y in range(64):
        draw.line((0, y, 63, y), fill=_blend(sky_top, sky_bottom, min(1, y / 32)))
    draw.ellipse((43, 9, 54, 20), fill=palette["sun"])
    camera_z = phase * MAP_SIZE
    camera_x = 64 + 14 * math.sin(math.tau * phase) + 5 * math.sin(2 * math.tau * phase)
    hidden = [64] * 64
    for depth in range(2, 100):
        map_z = (camera_z + depth) % MAP_SIZE
        z0 = int(map_z)
        z1 = (z0 + 1) % MAP_SIZE
        fraction_z = map_z - z0
        for screen_x in range(64):
            map_x = (camera_x + (screen_x - 31.5) * depth / 47) % MAP_SIZE
            x0 = int(map_x)
            x1 = (x0 + 1) % MAP_SIZE
            fraction_x = map_x - x0
            near = heights[z0][x0] * (1 - fraction_x) + heights[z0][x1] * fraction_x
            far = heights[z1][x0] * (1 - fraction_x) + heights[z1][x1] * fraction_x
            height = near * (1 - fraction_z) + far * fraction_z
            top = max(0, min(64, round(22 + (21 - height) * 54 / depth)))
            bottom = hidden[screen_x]
            if top < bottom:
                color = colors[z0][x0]
                haze = min(0.85, (depth / 110) ** 1.4)
                color = _blend(color, sky_bottom, haze)
                draw.line((screen_x, top, screen_x, bottom - 1), fill=color)
                hidden[screen_x] = top
    return image


def render(
    settings: Settings, config: dict[str, str], output: Path, output_large: Path
) -> None:
    palette_name = config.get("palette", "dusk")
    if palette_name not in PALETTES:
        raise ValueError(f"Unknown landscape palette '{palette_name}'.")
    seed = int(config["seed"]) if config.get("seed") else random.randint(1, 99999)
    palette = PALETTES[palette_name]
    heights, colors = _terrain(seed, palette)
    frames = [
        _frame(heights, colors, palette, index / FRAME_COUNT)
        for index in range(FRAME_COUNT)
    ]
    durations = [FRAME_DELAY_MS] * FRAME_COUNT
    frames[0].save(
        output,
        "WEBP",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        lossless=True,
    )
    large = [
        frame.resize(
            (64 * settings.magnification, 64 * settings.magnification),
            Image.Resampling.NEAREST,
        )
        for frame in frames
    ]
    large[0].save(
        output_large,
        "WEBP",
        save_all=True,
        append_images=large[1:],
        duration=durations,
        loop=0,
        lossless=True,
    )
