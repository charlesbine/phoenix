"""Procedural pixel planet generator.

Port of Deep-Fold's Pixel Planet Generator shaders to pure Python/Pillow.
Original: https://github.com/Deep-Fold/PixelPlanets (MIT License)
JS port reference: https://github.com/Timur310/PixelPlanets
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field
from typing import Sequence

from PIL import Image


# ---------------------------------------------------------------------------
# Core math (direct port of the GLSL functions)
# ---------------------------------------------------------------------------

def _rand(x: float, y: float, seed: float, size: float = 10.0) -> float:
    """Hash function matching the shader's rand()."""
    x = x % math.floor(size + 0.5)
    y = y % math.floor(size + 0.5)
    return math.fmod(math.sin(x * 12.9898 + y * 78.233) * 15.5453 * seed, 1.0) % 1.0


def _noise(x: float, y: float, seed: float, size: float = 10.0) -> float:
    """Value noise with cubic interpolation."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy

    a = _rand(ix, iy, seed, size)
    b = _rand(ix + 1, iy, seed, size)
    c = _rand(ix, iy + 1, seed, size)
    d = _rand(ix + 1, iy + 1, seed, size)

    cx = fx * fx * (3.0 - 2.0 * fx)
    cy = fy * fy * (3.0 - 2.0 * fy)

    return (a + (b - a) * cx + (c - a) * cy * (1.0 - cx) + (d - b) * cx * cy)


def _fbm(x: float, y: float, seed: float, octaves: int = 6, size: float = 10.0) -> float:
    """Fractional Brownian Motion."""
    value = 0.0
    scale = 0.5
    for _ in range(octaves):
        value += _noise(x, y, seed, size) * scale
        x *= 2.0
        y *= 2.0
        scale *= 0.5
    return value


def _circle_noise(x: float, y: float, seed: float, size: float = 10.0) -> float:
    """Circle-based noise for clouds and craters."""
    uy = math.floor(y)
    x += uy * 0.31
    fx, fy = x % 1.0, y % 1.0
    h = _rand(math.floor(x), math.floor(uy), seed, size)
    m = math.sqrt((fx - 0.25 - h * 0.5) ** 2 + (fy - 0.25 - h * 0.5) ** 2)
    r = h * 0.25
    if r <= 0:
        return 1.0
    return _smoothstep(0.0, r, m * 0.75)


def _planet_uv(ux: float, uy: float, phase: float) -> tuple[float, float]:
    """Project the visible hemisphere onto a texture that repeats in longitude."""
    x, y = ux * 2.0 - 1.0, uy * 2.0 - 1.0
    z = math.sqrt(max(0.0, 1.0 - x * x - y * y))
    longitude = math.atan2(x, z) / math.tau
    latitude = math.asin(_clamp(y, -1.0, 1.0)) / math.pi
    return (0.5 + longitude + phase) % 1.0, 0.5 + latitude


def _rotate(ux: float, uy: float, angle: float) -> tuple[float, float]:
    """2D rotation around center."""
    ux -= 0.5
    uy -= 0.5
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rx = ux * cos_a - uy * sin_a
    ry = ux * sin_a + uy * cos_a
    return rx + 0.5, ry + 0.5


def _pixelize(px: int, py: int, img_size: int, pixels: float) -> tuple[float, float]:
    """Convert pixel coords to pixelized UV matching shader behavior.

    In the shader, vUv ranges -0.5..0.5 (plane geometry coords).
    uv = floor(vUv * pixels) / pixels + 0.5  maps to 0..1 quantized.
    """
    vx = px / img_size - 0.5
    vy = py / img_size - 0.5
    ux = math.floor(vx * pixels) / pixels + 0.5
    uy = math.floor(vy * pixels) / pixels + 0.5
    return ux, uy


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _mix(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Color types
# ---------------------------------------------------------------------------

Color = tuple[int, int, int, int]  # RGBA 0-255


def _color(r: float, g: float, b: float, a: float = 1.0) -> Color:
    """Convert 0-1 floats to 0-255 RGBA."""
    return (
        int(_clamp(r) * 255),
        int(_clamp(g) * 255),
        int(_clamp(b) * 255),
        int(_clamp(a) * 255),
    )


def _mix_color(c1: Color, c2: Color, t: float) -> Color:
    t = _clamp(t)
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
        int(c1[3] + (c2[3] - c1[3]) * t),
    )


TRANSPARENT = (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Layer rendering
# ---------------------------------------------------------------------------

@dataclass
class LayerResult:
    """A rendered layer: 2D array of RGBA pixels."""
    pixels: list[list[Color]]
    size: int


def _composite(bottom: LayerResult, top: LayerResult) -> LayerResult:
    """Alpha-composite top layer over bottom."""
    s = bottom.size
    result = LayerResult(pixels=[[TRANSPARENT] * s for _ in range(s)], size=s)
    for y in range(s):
        for x in range(s):
            bg = bottom.pixels[y][x]
            fg = top.pixels[y][x]
            fa = fg[3] / 255.0
            ba = bg[3] / 255.0
            oa = fa + ba * (1.0 - fa)
            if oa <= 0:
                result.pixels[y][x] = TRANSPARENT
            else:
                result.pixels[y][x] = (
                    int((fg[0] * fa + bg[0] * ba * (1.0 - fa)) / oa),
                    int((fg[1] * fa + bg[1] * ba * (1.0 - fa)) / oa),
                    int((fg[2] * fa + bg[2] * ba * (1.0 - fa)) / oa),
                    int(oa * 255),
                )
    return result


def _render_base_planet(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    light_intensity: float,
    colors: Sequence[Color],
    octaves: int = 20,
) -> LayerResult:
    """Render the base planet layer (solid sphere with noise + lighting)."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin

    for py in range(size):
        for px in range(size):
            # Pixelize UV
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)

            # Dither
            dith = ((ux + (py / size - 0.5)) % (2.0 / pixels)) <= (1.0 / pixels)

            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            fbm1 = _fbm(ux * 10.0, uy * 10.0, seed, octaves)
            d_light_mod = d_light + _fbm(
                ux * 10.0 + fbm1,
                uy * 10.0,
                seed, octaves,
            ) * light_intensity

            light_border_1 = 0.4
            light_border_2 = 0.6
            dither_border = (1.0 / pixels) * 2.0

            col = colors[0]
            if d_light_mod > light_border_1:
                col = colors[1]
                if d_light_mod < light_border_1 + dither_border and dith:
                    col = colors[0]
            if d_light_mod > light_border_2:
                col = colors[2]
                if d_light_mod < light_border_2 + dither_border and dith:
                    col = colors[1]

            result.pixels[py][px] = col
    return result


def _render_land_mass(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    land_cutoff: float = 0.6,
    octaves: int = 6,
) -> LayerResult:
    """Render land mass layer."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            bx = ux * 10.0
            by = uy * 10.0

            fbm1 = _fbm(bx, by, seed, octaves)
            fbm2 = _fbm(bx - lx * fbm1, by - ly * fbm1, seed, octaves)
            fbm3 = _fbm(bx - lx * 1.5 * fbm1, by - ly * 1.5 * fbm1, seed, octaves)
            fbm4 = _fbm(bx - lx * 2.0 * fbm1, by - ly * 2.0 * fbm1, seed, octaves)

            light_border_1, light_border_2 = 0.4, 0.6
            if d_light < light_border_1:
                fbm4 *= 0.9
            if d_light > light_border_1:
                fbm2 *= 1.05
                fbm3 *= 1.05
                fbm4 *= 1.05
            if d_light > light_border_2:
                fbm2 *= 1.3
                fbm3 *= 1.4
                fbm4 *= 1.8

            d_light_sq = d_light ** 2 * 0.1
            col = colors[3]
            if fbm4 + d_light_sq < fbm1:
                col = colors[2]
            if fbm3 + d_light_sq < fbm1:
                col = colors[1]
            if fbm2 + d_light_sq < fbm1:
                col = colors[0]

            a = 1.0 if fbm1 >= land_cutoff else 0.0
            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_crater_layer(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
) -> LayerResult:
    """Render crater layer."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin
    crater_size = 5.0

    def _crater(ux: float, uy: float) -> float:
        c = 1.0
        for i in range(2):
            cn = _circle_noise(
                ux * crater_size + float(i + 1) + 10.0,
                uy * crater_size + float(i + 1) + 10.0,
                seed, crater_size,
            )
            c *= cn
        return 1.0 - c

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.5:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            c1 = _crater(ux, uy)
            c2 = _crater(ux + (lx - 0.5) * 0.04, uy + (ly - 0.5) * 0.04)

            col = colors[0]
            a = 1.0 if c1 >= 0.5 else 0.0

            if c2 < c1 - (0.5 - d_light) * 2.0:
                col = colors[1]
            if d_light > 0.4:
                col = colors[1]

            if d_circle > 0.5:
                a = 0.0

            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_cloud_layer(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    cloud_cover: float = 0.546,
    stretch: float = 2.5,
    noise_size: float = 4.0,
    octaves: int = 4,
) -> LayerResult:
    """Render cloud layer."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin

    def _cloud_alpha(ux: float, uy: float) -> float:
        c_noise = 0.0
        for i in range(9):
            c_noise += _circle_noise(
                ux * noise_size + float(i + 1) + 10.0,
                uy * noise_size * 0.3 + float(i + 1) + 10.0,
                seed, noise_size,
            )
        return _fbm(
            ux * noise_size + c_noise,
            uy * noise_size + c_noise,
            seed, octaves, noise_size,
        )

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.5:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            d_to_center = d_circle

            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            c = _cloud_alpha(ux, uy * stretch)

            col = colors[0]  # base_color
            if c < cloud_cover + 0.03:
                col = colors[1]  # outline_color
            if d_light + c * 0.2 > 0.4:
                col = colors[2]  # shadow_base_color
            if d_light + c * 0.2 > 0.6:
                col = colors[3]  # shadow_outline_color

            a = 1.0 if c >= cloud_cover else 0.0
            a *= 1.0 if d_to_center <= 0.5 else 0.0

            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_atmosphere(
    size: int,
    pixels: float,
    colors: Sequence[Color],
) -> LayerResult:
    """Render atmosphere glow ring."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            cx = ux * 2.0 - 1.0
            cy = uy * 2.0 - 1.0
            dist = math.sqrt(cx * cx + cy * cy)

            c = _mix_color(TRANSPARENT, colors[0], _smoothstep(0.65, 0.87, dist))
            c = _mix_color(c, colors[1], _smoothstep(0.87, 0.97, dist))
            c = _mix_color(c, colors[2], _smoothstep(0.97, 1.04, dist))
            c = _mix_color(c, TRANSPARENT, _smoothstep(1.04, 1.04, dist))

            if c[3] > 0:
                result.pixels[py][px] = c
    return result


def _render_lake_layer(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    lake_cutoff: float = 0.6,
    octaves: int = 4,
) -> LayerResult:
    """Render lake/water layer."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.5:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            lake = _fbm(ux * 10.0, uy * 10.0, seed, octaves)

            col = colors[0]
            if d_light > 0.4:
                col = colors[1]
            if d_light > 0.6:
                col = colors[2]

            a = 1.0 if lake >= lake_cutoff else 0.0
            if d_circle > 0.5:
                a = 0.0

            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_river_layer(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    river_cutoff: float = 0.6,
    octaves: int = 5,
) -> LayerResult:
    """Render river/lava flow layer."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            fbm1 = _fbm(ux * 10.0, uy * 10.0, seed, octaves)
            river_fbm = _fbm(ux * 10.0 + fbm1 * 2.5, uy + fbm1 * 2.5, seed, octaves)

            col = colors[0]
            if d_light > 0.4:
                col = colors[1]
            if d_light > 0.6:
                col = colors[2]

            a = 1.0 if river_fbm >= river_cutoff else 0.0
            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_gas_base(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    cloud_cover: float = 0.0,
    stretch: float = 1.0,
    octaves: int = 5,
) -> LayerResult:
    """Render gas giant base (cloud bands)."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin
    noise_size = 9.0

    def _cloud_alpha(ux: float, uy: float) -> float:
        c_noise = 0.0
        for i in range(9):
            c_noise += _circle_noise(
                ux * noise_size + float(i + 1) + 10.0,
                uy * noise_size * 0.3 + float(i + 1) + 10.0,
                seed, noise_size,
            )
        return _fbm(
            ux * noise_size + c_noise,
            uy * noise_size + c_noise,
            seed, octaves, noise_size,
        )

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            c = _cloud_alpha(ux, uy * stretch)

            col = colors[0]
            if c < cloud_cover + 0.03:
                col = colors[1]
            if d_light + c * 0.2 > 0.4:
                col = colors[2]
            if d_light + c * 0.2 > 0.6:
                col = colors[3]

            result.pixels[py][px] = col
    return result


def _render_gas_layer(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    light_origin: tuple[float, float],
    colors: Sequence[Color],
    cloud_cover: float = 0.538,
    stretch: float = 1.0,
    octaves: int = 5,
) -> LayerResult:
    """Render gas giant overlay bands."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    lx, ly = light_origin
    noise_size = 9.0

    def _cloud_alpha(ux: float, uy: float) -> float:
        c_noise = 0.0
        for i in range(9):
            c_noise += _circle_noise(
                ux * noise_size + float(i + 1) + 10.0,
                uy * noise_size * 0.3 + float(i + 1) + 10.0,
                seed, noise_size,
            )
        return _fbm(
            ux * noise_size + c_noise,
            uy * noise_size + c_noise,
            seed, octaves, noise_size,
        )

    for py in range(size):
        for px in range(size):
            ux, uy = _pixelize(px, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            d_light = math.sqrt((ux - lx) ** 2 + (uy - ly) ** 2)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            c = _cloud_alpha(ux, uy * stretch)

            col = colors[0]
            if c < cloud_cover + 0.03:
                col = colors[1]
            if d_light + c * 0.2 > 0.4:
                col = colors[2]
            if d_light + c * 0.2 > 0.6:
                col = colors[3]

            a = 1.0 if c >= cloud_cover else 0.0
            if a > 0:
                result.pixels[py][px] = (col[0], col[1], col[2], int(a * col[3]))
    return result


def _render_star_body(
    size: int,
    pixels: float,
    seed: float,
    phase: float,
    rotation: float,
    colors: Sequence[Color],
    octaves: int = 5,
) -> LayerResult:
    """Render star body using cellular noise."""
    result = LayerResult(pixels=[[TRANSPARENT] * size for _ in range(size)], size=size)
    tiles = 2.0

    def _hash2(px: float, py: float) -> tuple[float, float]:
        r = 523.0 * math.sin(px * 53.3158 + py * 43.6143)
        return (r * 15.32354) % 1.0, (r * 17.25865) % 1.0

    def _cells(px: float, py: float, num_cells: float) -> float:
        px *= num_cells
        py *= num_cells
        d = 1e10
        for xo in range(-1, 2):
            for yo in range(-1, 2):
                tpx = math.floor(px) + xo
                tpy = math.floor(py) + yo
                hx, hy = _hash2(tpx % (num_cells / tiles), tpy % (num_cells / tiles))
                dx = px - tpx - hx
                dy = py - tpy - hy
                d = min(d, dx * dx + dy * dy)
        return math.sqrt(d)

    for py in range(size):
        for px_i in range(size):
            ux, uy = _pixelize(px_i, py, size, pixels)

            d_circle = math.sqrt((ux - 0.5) ** 2 + (uy - 0.5) ** 2)
            if d_circle > 0.49999:
                continue

            dith = ((px_i / size - 0.5 + py / size - 0.5) % (2.0 / pixels)) <= (1.0 / pixels)
            ux, uy = _rotate(ux, uy, rotation)
            ux, uy = _planet_uv(ux, uy, phase)

            n = _cells(ux, uy, 10.0)
            n *= _cells(ux, uy, 20.0)
            n *= 2.0
            n = _clamp(n)
            if dith:
                n *= 1.3

            idx = int(_clamp(math.floor(n * 3.0) / 3.0) * (len(colors) - 1))
            col = colors[min(idx, len(colors) - 1)]
            result.pixels[py][px_i] = col
    return result


# ---------------------------------------------------------------------------
# Planet type definitions
# ---------------------------------------------------------------------------

@dataclass
class PlanetConfig:
    planet_type: str
    seed: float = field(default_factory=lambda: random.random() * 100)
    size: int = 50  # virtual pixel resolution
    image_size: int = 64
    rotation: float = 0.0
    light_origin: tuple[float, float] = (0.39, 0.7)
    light_intensity: float = 0.1
    n_frames: int = 50
    frame_delay_ms: int = 200
    # Per-type overrides (None = use defaults)
    cloud_cover: float | None = None
    land_cutoff: float | None = None
    colors: list[list[Color]] | None = None  # list of palettes per layer


def _layer_to_image(layer: LayerResult, image_size: int) -> Image.Image:
    img = Image.new("RGBA", (layer.size, layer.size), (0, 0, 0, 0))
    for y in range(layer.size):
        for x in range(layer.size):
            img.putpixel((x, y), layer.pixels[y][x])
    if layer.size != image_size:
        img = img.resize((image_size, image_size), Image.NEAREST)
    return img


def generate_terran_wet(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Earth-like planet with oceans, land, and clouds."""
    palettes = cfg.colors or [
        [_color(0.4, 0.69, 0.78), _color(0.4, 0.69, 0.78), _color(0.2, 0.25, 0.62)],
        [_color(0.78, 0.83, 0.36), _color(0.39, 0.67, 0.25),
         _color(0.18, 0.34, 0.33), _color(0.16, 0.21, 0.25)],
        [_color(0.88, 0.95, 1.0), _color(0.75, 0.89, 1.0),
         _color(0.37, 0.44, 0.65), _color(0.25, 0.29, 0.45)],
        [_color(0.68, 0.85, 0.9, 0.25), _color(0.0, 0.5, 1.0, 0.35),
         _color(0.0, 0.0, 0.5, 0.45)],
    ]
    base_colors, land_colors = palettes[0], palettes[1]
    cloud_colors = palettes[2] if len(palettes) > 2 else palettes[0]
    atmo_colors = palettes[3] if len(palettes) > 3 else [_color(0.68, 0.85, 0.9, 0.25), _color(0.0, 0.5, 1.0, 0.35), _color(0.0, 0.0, 0.5, 0.45)]

    seed2 = cfg.seed + 10
    seed3 = cfg.seed + 20
    land_cut = cfg.land_cutoff if cfg.land_cutoff is not None else 0.5
    cloud_cov = cfg.cloud_cover if cfg.cloud_cover is not None else 0.546

    base = _render_base_planet(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                                cfg.light_origin, cfg.light_intensity, base_colors)
    land = _render_land_mass(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                              cfg.light_origin, land_colors, land_cutoff=land_cut)
    clouds = _render_cloud_layer(cfg.size, cfg.size, seed3, phase, cfg.rotation,
                                  cfg.light_origin, cloud_colors, cloud_cover=cloud_cov)
    atmo = _render_atmosphere(cfg.size, cfg.size, atmo_colors)

    comp = _composite(base, land)
    comp = _composite(comp, clouds)
    comp = _composite(comp, atmo)
    return _layer_to_image(comp, cfg.image_size)


def generate_no_atmosphere(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Barren moon/planet with craters."""
    palettes = cfg.colors or [
        [_color(0.61, 0.62, 0.72), _color(0.28, 0.38, 0.49), _color(0.21, 0.22, 0.33)],
        [_color(0.28, 0.38, 0.49), _color(0.21, 0.22, 0.33)],
    ]

    seed2 = cfg.seed + 10

    base = _render_base_planet(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                                cfg.light_origin, cfg.light_intensity, palettes[0])
    craters = _render_crater_layer(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                                    cfg.light_origin, palettes[1] if len(palettes) > 1 else palettes[0][:2])

    comp = _composite(base, craters)
    return _layer_to_image(comp, cfg.image_size)


def generate_lava(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Lava planet with rivers of molten rock."""
    palettes = cfg.colors or [
        [_color(0.56, 0.30, 0.34), _color(0.32, 0.20, 0.25), _color(0.24, 0.16, 0.21)],
        [_color(0.32, 0.20, 0.25), _color(0.24, 0.16, 0.21)],
        [_color(1.0, 0.54, 0.2), _color(0.90, 0.27, 0.22), _color(0.68, 0.18, 0.27)],
    ]

    seed2 = cfg.seed + 10
    seed3 = cfg.seed + 20

    base = _render_base_planet(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                                cfg.light_origin, cfg.light_intensity, palettes[0])
    craters = _render_crater_layer(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                                    cfg.light_origin, palettes[1] if len(palettes) > 1 else palettes[0][:2])
    rivers = _render_river_layer(cfg.size, cfg.size, seed3, phase, cfg.rotation,
                                  cfg.light_origin, palettes[2] if len(palettes) > 2 else palettes[0], river_cutoff=0.55)

    comp = _composite(base, craters)
    comp = _composite(comp, rivers)
    return _layer_to_image(comp, cfg.image_size)


def generate_ice(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Ice world with frozen lakes and clouds."""
    palettes = cfg.colors or [
        [_color(0.98, 1.0, 1.0), _color(0.78, 0.83, 1.0), _color(0.57, 0.56, 0.72)],
        [_color(0.31, 0.64, 0.72), _color(0.30, 0.41, 0.52), _color(0.23, 0.25, 0.37)],
        [_color(0.88, 0.95, 1.0), _color(0.75, 0.89, 1.0),
         _color(0.37, 0.44, 0.65), _color(0.25, 0.29, 0.45)],
    ]

    seed2 = cfg.seed + 10
    seed3 = cfg.seed + 20
    cloud_cov = cfg.cloud_cover if cfg.cloud_cover is not None else 0.546

    base = _render_base_planet(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                                cfg.light_origin, cfg.light_intensity, palettes[0])
    lakes = _render_lake_layer(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                                cfg.light_origin, palettes[1] if len(palettes) > 1 else palettes[0])
    clouds = _render_cloud_layer(cfg.size, cfg.size, seed3, phase, cfg.rotation,
                                  cfg.light_origin, palettes[2] if len(palettes) > 2 else palettes[0],
                                  cloud_cover=cloud_cov)

    comp = _composite(base, lakes)
    comp = _composite(comp, clouds)
    return _layer_to_image(comp, cfg.image_size)


def generate_gas_giant(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Gas giant with cloud bands."""
    palettes = cfg.colors or [
        [_color(0.94, 0.71, 0.25), _color(0.81, 0.46, 0.17),
         _color(0.67, 0.32, 0.19), _color(0.49, 0.22, 0.20)],
        [_color(0.23, 0.13, 0.15), _color(0.23, 0.13, 0.15),
         _color(0.13, 0.09, 0.11), _color(0.13, 0.09, 0.11)],
    ]
    cloud_cov = cfg.cloud_cover if cfg.cloud_cover is not None else 0.538

    seed2 = cfg.seed + 10

    base = _render_gas_base(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                             cfg.light_origin, palettes[0])
    gas = _render_gas_layer(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                             cfg.light_origin, palettes[1] if len(palettes) > 1 else palettes[0],
                             cloud_cover=cloud_cov)

    comp = _composite(base, gas)
    return _layer_to_image(comp, cfg.image_size)


def generate_star(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Blazing star with cellular pattern."""
    palettes = cfg.colors or [
        [_color(1.0, 0.95, 0.8), _color(1.0, 0.65, 0.0),
         _color(0.9, 0.27, 0.0), _color(0.5, 0.1, 0.0)],
    ]
    body = _render_star_body(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation, palettes[0])
    return _layer_to_image(body, cfg.image_size)


def generate_dry(cfg: PlanetConfig, phase: float) -> Image.Image:
    """Dry/desert planet."""
    palettes = cfg.colors or [
        [_color(0.78, 0.69, 0.42), _color(0.63, 0.48, 0.32), _color(0.43, 0.33, 0.27)],
        [_color(0.50, 0.38, 0.30), _color(0.35, 0.25, 0.22)],
    ]

    seed2 = cfg.seed + 10

    base = _render_base_planet(cfg.size, cfg.size, cfg.seed, phase, cfg.rotation,
                                cfg.light_origin, cfg.light_intensity, palettes[0], octaves=4)
    craters = _render_crater_layer(cfg.size, cfg.size, seed2, phase, cfg.rotation,
                                    cfg.light_origin, palettes[1] if len(palettes) > 1 else palettes[0][:2])

    comp = _composite(base, craters)
    return _layer_to_image(comp, cfg.image_size)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

PLANET_TYPES = {
    "terran_wet": generate_terran_wet,
    "no_atmosphere": generate_no_atmosphere,
    "lava": generate_lava,
    "ice": generate_ice,
    "gas_giant": generate_gas_giant,
    "star": generate_star,
    "dry": generate_dry,
}


def _parse_hex_color(hex_str: str) -> Color:
    """Parse '#RRGGBB' or '#RRGGBBAA' to RGBA tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 6:
        return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), 255)
    if len(hex_str) == 8:
        return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), int(hex_str[6:8], 16))
    raise ValueError(f"Invalid hex color: #{hex_str}")


def _parse_colors(raw: list[list[str]] | None) -> list[list[Color]] | None:
    """Parse nested list of hex color strings to Color tuples."""
    if raw is None:
        return None
    return [[_parse_hex_color(c) for c in palette] for palette in raw]


DEFAULT_ANIMATION_SPEED = 0.1
MIN_ANIMATION_SPEED = 0.08
MAX_ANIMATION_SPEED = 0.16
MIN_FRAMES_PER_TURN = 100
# GIF durations are stored in centiseconds.
MIN_FRAME_DELAY_CS = 4
MAX_FRAME_DELAY_CS = 7
MIN_TURN_DURATION_CS = 500
MAX_TURN_DURATION_CS = 1500


def generate_planet_gif(
    planet_type: str | None = None,
    seed: int | None = None,
    size: int = 64,
    n_frames: int = 50,
    frame_delay_ms: int = 200,
    light_origin: tuple[float, float] | None = None,
    rotation: float | None = None,
    time_speed: float = DEFAULT_ANIMATION_SPEED,
    cloud_cover: float | None = None,
    land_cutoff: float | None = None,
    colors: list[list[str]] | None = None,
) -> bytes:
    """Generate a seamless animated GIF of a procedural pixel planet.

    Args:
        planet_type: One of PLANET_TYPES keys, or None for random.
        seed: Random seed for reproducibility. None for random.
        size: Output image size in pixels.
        n_frames: Preferred frame count. One frame renders a still planet.
        frame_delay_ms: Reference frame delay used with n_frames to set the turn duration.
        light_origin: (x, y) position of light source, 0-1. None for default (0.39, 0.7).
        rotation: Planet tilt in radians. None for random.
        time_speed: Playback speed relative to 0.1. Nonzero magnitudes are
                    clamped to 0.08–0.16. Negative values reverse rotation.
        cloud_cover: Cloud density 0-1. None for type default.
        land_cutoff: Land vs water threshold 0-1. None for type default.
        colors: Per-layer color palettes as nested hex strings, e.g.
                [["#FF0000", "#00FF00"], ["#0000FF"]]. None for type defaults.

    Returns:
        GIF file contents as bytes.
    """
    if planet_type is None:
        planet_type = random.choice(list(PLANET_TYPES.keys()))
    if seed is None:
        seed = random.randint(1, 99999)

    if not math.isfinite(time_speed):
        raise ValueError("Animation speed must be finite.")
    if n_frames < 1 or frame_delay_ms < 1:
        raise ValueError("Frame count and delay must be positive.")

    direction = -1.0 if time_speed < 0 else 1.0
    if time_speed == 0 or n_frames == 1:
        n_frames = 1
        durations = [0]
    else:
        speed = _clamp(abs(time_speed), MIN_ANIMATION_SPEED, MAX_ANIMATION_SPEED)
        reference_duration_cs = n_frames * frame_delay_ms / 10
        turn_duration_cs = round(_clamp(
            reference_duration_cs * DEFAULT_ANIMATION_SPEED / speed,
            MIN_TURN_DURATION_CS,
            MAX_TURN_DURATION_CS,
        ))
        # Slow rotation needs more samples across the turn. Fast rotation still
        # needs enough samples to keep each longitude step small.
        min_frames = max(MIN_FRAMES_PER_TURN, math.ceil(turn_duration_cs / MAX_FRAME_DELAY_CS))
        max_frames = turn_duration_cs // MIN_FRAME_DELAY_CS
        n_frames = min(max(n_frames, min_frames), max_frames)
        boundaries = [i * turn_duration_cs // n_frames for i in range(n_frames + 1)]
        durations = [(end - start) * 10 for start, end in zip(boundaries, boundaries[1:])]

    generator = PLANET_TYPES[planet_type]
    rng = random.Random(seed)
    cfg = PlanetConfig(
        planet_type=planet_type,
        seed=rng.random() * 100,
        size=size,
        image_size=size,
        rotation=rotation if rotation is not None else rng.uniform(0, 6.28),
        light_origin=light_origin or (0.39, 0.7),
        n_frames=n_frames,
        frame_delay_ms=frame_delay_ms,
        cloud_cover=cloud_cover,
        land_cutoff=land_cutoff,
        colors=_parse_colors(colors),
    )

    frames: list[Image.Image] = []
    # Sample at each frame's actual start time after GIF timing is rounded.
    turn_duration_ms = sum(durations) or 1
    elapsed_ms = 0
    for delay_ms in durations:
        phase = direction * elapsed_ms / turn_duration_ms
        frame = generator(cfg, phase)
        elapsed_ms += delay_ms
        # Convert to RGB with black background for GIF
        bg = Image.new("RGBA", (size, size), (0, 0, 0, 255))
        bg.paste(frame, (0, 0), frame)
        frames.append(bg.convert("RGB"))

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    return buf.getvalue()


if __name__ == "__main__":
    import sys

    planet_type = sys.argv[1] if len(sys.argv) > 1 else None
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else None
    gif_bytes = generate_planet_gif(planet_type=planet_type, seed=seed)
    out_name = f"planet_{planet_type or 'random'}_{seed or 'random'}.gif"
    with open(out_name, "wb") as f:
        f.write(gif_bytes)
    print(f"Wrote {out_name} ({len(gif_bytes)} bytes)")
