"""A continuous flight over a seeded, wrapping generative pixel landscape."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from phoenix.settings import Settings

PALETTES: dict[str, dict] = {
    "dusk": {
        "sky": ("#151232", "#c86882"),
        "sky_mid": "#4e2d62",
        "sun": "#ffcb7d",
        "water": "#3c497e",
        "shore": "#d8989e",
        "land": ("#292b47", "#4c5878", "#839da3", "#f0d3ca"),
        "highlight": "#ffd9a8",
        "shadow": "#10112a",
        "shimmer": "#ffd596",
        "celestials": ("sun_glow", "crescent"),
        "stars": True,
        "clouds": True,
    },
    "alpine": {
        "sky": ("#0f2b52", "#8fc8da"),
        "sky_mid": "#2c6ba0",
        "sun": "#fff0b8",
        "water": "#206286",
        "shore": "#b5c294",
        "land": ("#1d3d35", "#3d6b4f", "#849a8e", "#f6f4ee"),
        "highlight": "#fff5d8",
        "shadow": "#0f1f30",
        "shimmer": "#fff4cc",
        "celestials": ("sun_glow",),
        "stars": False,
        "clouds": True,
    },
    "alien": {
        "sky": ("#140a2c", "#a84c86"),
        "sky_mid": "#491c5d",
        "sun": "#ffbfa8",
        "water": "#3a2863",
        "shore": "#d68aa8",
        "land": ("#241c42", "#4d3d78", "#8393a8", "#eccbc0"),
        "highlight": "#f8c8e2",
        "shadow": "#0c061c",
        "shimmer": "#ffb8dc",
        "celestials": ("ringed", "ringed", "twin_moons"),
        "stars": True,
        "clouds": False,
    },
    "sunset": {
        "sky": ("#131038", "#ff7040"),
        "sky_mid": "#8c2654",
        "sun": "#ffe878",
        "water": "#ad483a",
        "shore": "#f5a45b",
        "land": ("#23142e", "#522444", "#a44548", "#ffb266"),
        "highlight": "#ffdf7c",
        "shadow": "#12081b",
        "shimmer": "#ffea88",
        "celestials": ("sun_glow",),
        "stars": False,
        "clouds": True,
    },
    "synthwave": {
        "sky": ("#0b0322", "#ff2684"),
        "sky_mid": "#450b6a",
        "sun": "#ffdc42",
        "water": "#1a0c40",
        "shore": "#26c6e8",
        "land": ("#170b36", "#3d1672", "#9e26ba", "#4ef0ff"),
        "highlight": "#66f4ff",
        "shadow": "#080318",
        "shimmer": "#ff5cc0",
        "celestials": ("synth_sun",),
        "stars": True,
        "clouds": False,
        "neon_crest": "#4ef0ff",
    },
    "aurora": {
        "sky": ("#040a18", "#12344d"),
        "sky_mid": "#081a30",
        "sun": "#dcf6ff",
        "water": "#0c243b",
        "shore": "#449cb0",
        "land": ("#102336", "#1d4c5e", "#48a2a6", "#e4f8ff"),
        "highlight": "#80f8dc",
        "shadow": "#050d1b",
        "shimmer": "#58f5c4",
        "aurora": ("#1eff9c", "#2ae0ff", "#8a5cff"),
        "celestials": ("aurora_stars", "crescent"),
        "stars": True,
        "clouds": False,
    },
    "volcanic": {
        "sky": ("#12080c", "#b82c18"),
        "sky_mid": "#4a1414",
        "sun": "#ff7024",
        "water": "#ff5400",
        "shore": "#ffaa1c",
        "land": ("#151014", "#291e22", "#4e2c26", "#c74a22"),
        "highlight": "#ff7e2e",
        "shadow": "#080406",
        "shimmer": "#ffe066",
        "lava_core": "#ffe258",
        "celestials": ("ember_sun", "crescent"),
        "stars": True,
        "clouds": True,
    },
    "desert": {
        "sky": ("#244678", "#f7b274"),
        "sky_mid": "#8c6d8a",
        "sun": "#fff0a6",
        "water": "#26868c",
        "shore": "#e8c882",
        "land": ("#7a3624", "#b8552e", "#df8742", "#f6d286"),
        "highlight": "#ffeaa8",
        "shadow": "#341418",
        "shimmer": "#fff2b8",
        "celestials": ("sun_glow",),
        "stars": False,
        "clouds": True,
    },
    "sakura": {
        "sky": ("#1b153e", "#f29ab8"),
        "sky_mid": "#683b76",
        "sun": "#ffe4d6",
        "water": "#4a3b73",
        "shore": "#f8bed4",
        "land": ("#2b2048", "#6e4174", "#d87ba8", "#ffe6f0"),
        "highlight": "#ffebf4",
        "shadow": "#140d2c",
        "shimmer": "#ffd2e6",
        "celestials": ("sun_glow", "crescent"),
        "stars": False,
        "clouds": True,
    },
    "emerald": {
        "sky": ("#124a6e", "#f2d08c"),
        "sky_mid": "#3c8ea3",
        "sun": "#fff3b0",
        "water": "#0c8c94",
        "shore": "#f2da9e",
        "land": ("#124232", "#1e754a", "#5eab56", "#dceaa0"),
        "highlight": "#fff6c2",
        "shadow": "#092522",
        "shimmer": "#c8fff4",
        "celestials": ("sun_glow",),
        "stars": False,
        "clouds": True,
    },
    "moonlight": {
        "sky": ("#050a1e", "#284878"),
        "sky_mid": "#0e2047",
        "sun": "#eaf3ff",
        "water": "#11264a",
        "shore": "#6c8cb6",
        "land": ("#121d36", "#273c60", "#5d7ca2", "#edf5ff"),
        "highlight": "#d8ecff",
        "shadow": "#060b1a",
        "shimmer": "#dceeff",
        "celestials": ("crescent",),
        "stars": True,
        "clouds": False,
    },
    "mars": {
        "sky": ("#281012", "#d87042"),
        "sky_mid": "#752a20",
        "sun": "#ffd9b0",
        "water": "#461e1a",
        "shore": "#9e432b",
        "land": ("#4d1d19", "#8c3724", "#c65d32", "#ee9e64"),
        "highlight": "#ffcd96",
        "shadow": "#1f080a",
        "shimmer": "#e08c5a",
        "celestials": ("twin_moons", "ringed"),
        "stars": True,
        "clouds": False,
    },
}

TERRAINS: tuple[str, ...] = (
    "fjord",
    "peaks",
    "canyon",
    "dunes",
    "archipelago",
    "coast",
)

_TERRAIN_AFFINITIES: dict[str, tuple[str, ...]] = {
    "dusk": ("coast", "canyon", "archipelago", "dunes"),
    "alpine": ("peaks", "coast", "fjord"),
    "alien": ("canyon", "peaks", "dunes", "archipelago"),
    "sunset": ("coast", "archipelago", "dunes"),
    "synthwave": ("fjord", "peaks", "canyon", "dunes"),
    "aurora": ("fjord", "coast", "peaks"),
    "volcanic": ("fjord", "canyon", "peaks"),
    "desert": ("dunes", "canyon"),
    "sakura": ("coast", "peaks", "archipelago"),
    "emerald": ("archipelago", "coast", "peaks"),
    "moonlight": ("peaks", "coast", "archipelago", "fjord"),
    "mars": ("canyon", "dunes", "peaks"),
}

SETTINGS_SCHEMA = [
    {
        "type": "dropdown",
        "id": "palette",
        "name": "World Palette",
        "default": "auto",
        "options": [
            {"value": "auto", "display": "Auto (Random World)"},
            *({"value": key, "display": key.title()} for key in PALETTES),
        ],
    },
    {
        "type": "dropdown",
        "id": "terrain",
        "name": "Terrain",
        "default": "auto",
        "options": [
            {"value": "auto", "display": "Auto (Random)"},
            *({"value": key, "display": key.title()} for key in TERRAINS),
        ],
    },
    {
        "type": "number",
        "id": "seed",
        "name": "Seed",
        "desc": "Leave empty for a new world each render.",
    },
]

MAP_SIZE = 128
FRAME_COUNT = 160
FRAME_DELAY_MS = 75

_FOV_DIV = 46.0
_PROJ_SCALE = 52.0
_DEFAULT_SWAY_A = 8.5
_DEFAULT_SWAY_B = 2.5
_DEFAULT_SWAY_PHASE = 0.0
_WATER_LEVEL = 2.0


def _build_depths() -> tuple[tuple[float, float, float, float], ...]:
    """Precompute adaptive near-to-far depth slices with (depth, c_lod, h_lod, haze_t)."""
    slices: list[tuple[float, float, float, float]] = []
    depth = 2.8
    while depth < 102.0:
        c_lod = math.log2(max(1.0, depth / 32.0))
        h_lod = math.log2(max(1.0, depth / 48.0))
        haze_t = (depth / 104.0) ** 1.65
        slices.append((depth, c_lod, h_lod, haze_t))
        depth += max(0.34, depth * 0.032)
    return tuple(slices)


_DEPTH_SLICES = _build_depths()
_SUB_W = 128
_X_OFFSETS = tuple(((sx + 0.5) * 0.5 - 32.0) / _FOV_DIV for sx in range(_SUB_W))


@dataclass(frozen=True)
class _SceneParams:
    seed: int
    palette_name: str
    terrain: str
    sway_a: float
    sway_b: float
    sway_phase: float
    horizon: float
    camera_height: float
    sun_x: float
    sun_y: float
    sun_r: float
    celestial: str
    has_aurora: bool
    has_stars: bool
    has_clouds: bool
    haze_max: float
    shimmer_strength: float
    is_lava: bool
    has_water_channel: bool
    coast_side: int = 1


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(bytes.fromhex(hex_color.lstrip("#")))  # type: ignore[return-value]


def _rgb_f(hex_color: str) -> tuple[float, float, float]:
    r, g, b = bytes.fromhex(hex_color.lstrip("#"))
    return (float(r), float(g), float(b))


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if value < lo else (hi if value > hi else value)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = _clamp((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _blend(first: tuple[int, int, int], second: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return (
        round(first[0] + (second[0] - first[0]) * amount),
        round(first[1] + (second[1] - first[1]) * amount),
        round(first[2] + (second[2] - first[2]) * amount),
    )


def _blend_f(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    amount: float,
) -> tuple[float, float, float]:
    return (
        first[0] + (second[0] - first[0]) * amount,
        first[1] + (second[1] - first[1]) * amount,
        first[2] + (second[2] - first[2]) * amount,
    )


def _palette_name_for(palette: dict) -> str:
    for name, candidate in PALETTES.items():
        if candidate is palette or candidate.get("sky") == palette.get("sky"):
            return name
    return "dusk"


def _resolve_palette_name(palette_config: str | None, seed: int) -> str:
    if not palette_config or palette_config == "auto":
        rng = random.Random(seed * 2654435761 + 17)
        names = tuple(PALETTES)
        return names[rng.randrange(len(names))]
    if palette_config not in PALETTES:
        raise ValueError(f"Unknown landscape palette '{palette_config}'.")
    return palette_config


def _resolve_terrain_name(terrain_config: str | None, seed: int, palette_name: str) -> str:
    if not terrain_config or terrain_config == "auto":
        rng = random.Random(seed * 1597334677 + sum(ord(ch) for ch in palette_name) * 97)
        affinities = _TERRAIN_AFFINITIES.get(palette_name, TERRAINS)
        if rng.random() < 0.85:
            return affinities[rng.randrange(len(affinities))]
        return TERRAINS[rng.randrange(len(TERRAINS))]
    if terrain_config not in TERRAINS:
        raise ValueError(f"Unknown landscape terrain '{terrain_config}'.")
    return terrain_config


def _build_scene(
    seed: int,
    palette_name: str,
    terrain: str,
    *,
    default_corridor: bool = False,
) -> _SceneParams:
    palette = PALETTES.get(palette_name, PALETTES["dusk"])
    rng = random.Random(seed * 3266489917 + sum(ord(c) for c in f"{palette_name}:{terrain}") * 31)
    coast_side = -1 if rng.random() < 0.5 else 1

    if default_corridor:
        sway_a = _DEFAULT_SWAY_A
        sway_b = _DEFAULT_SWAY_B
        sway_phase = _DEFAULT_SWAY_PHASE
    elif terrain == "fjord":
        sway_sign = -1.0 if rng.random() < 0.5 else 1.0
        sway_a = rng.uniform(6.0, 10.5) * sway_sign
        sway_b = rng.uniform(1.5, 3.6) * (-1.0 if rng.random() < 0.5 else 1.0)
        sway_phase = rng.uniform(0.0, math.tau)
    elif terrain == "coast":
        sway_sign = -1.0 if rng.random() < 0.5 else 1.0
        sway_a = rng.uniform(2.4, 4.2) * sway_sign
        sway_b = rng.uniform(0.4, 1.0) * (-1.0 if rng.random() < 0.5 else 1.0)
        sway_phase = rng.uniform(0.0, math.tau)
    else:
        sway_sign = -1.0 if rng.random() < 0.5 else 1.0
        sway_a = rng.uniform(1.8, 3.8) * sway_sign
        sway_b = rng.uniform(0.3, 0.9) * (-1.0 if rng.random() < 0.5 else 1.0)
        sway_phase = rng.uniform(0.0, math.tau)

    celestials = palette.get("celestials", ("sun_glow",))
    celestial = celestials[rng.randrange(len(celestials))]

    if celestial == "synth_sun":
        sun_x = rng.uniform(26.0, 38.0)
        sun_y = rng.uniform(16.0, 19.0)
        sun_r = rng.uniform(8.2, 9.4)
    elif celestial == "ringed":
        sun_x = rng.uniform(18.0, 46.0)
        sun_y = rng.uniform(9.5, 13.5)
        sun_r = rng.uniform(5.2, 6.4)
    elif celestial == "aurora_stars":
        sun_x = rng.uniform(16.0, 48.0)
        sun_y = rng.uniform(8.0, 13.0)
        sun_r = rng.uniform(4.2, 5.2)
    else:
        sun_x = rng.uniform(14.0, 50.0)
        sun_y = rng.uniform(9.5, 15.5)
        sun_r = rng.uniform(4.8, 6.6)

    # On coastline worlds, position the sun/moon over the ocean side so it lights the facing cliffs
    # and paints a shimmering reflection path across the open water.
    if terrain == "coast" and celestial != "synth_sun":
        sun_x = rng.uniform(11.0, 30.0) if coast_side > 0 else rng.uniform(34.0, 53.0)

    has_aurora = bool(palette.get("aurora")) or (
        palette_name in ("moonlight", "alien") and rng.random() < 0.25
    )
    has_stars = bool(palette.get("stars", False)) or has_aurora
    has_clouds = bool(palette.get("clouds", False)) and not has_aurora
    is_lava = palette_name == "volcanic"

    # Only fjord, archipelago, and coast feature open water; dunes and canyon are dry expanses,
    # and peaks only form natural scattered 2D alpine tarns without a carved channel.
    has_water_channel = terrain in ("fjord", "archipelago", "coast")

    horizon_map = {
        "fjord": 26.0,
        "peaks": 24.2,
        "canyon": 24.8,
        "dunes": 23.5,
        "archipelago": 25.2,
        "coast": 25.0,
    }
    cam_h_map = {
        "fjord": 17.5,
        "peaks": 21.0,
        "canyon": 15.8,
        "dunes": 18.2,
        "archipelago": 15.0,
        "coast": 16.0,
    }
    horizon = horizon_map.get(terrain, 26.0) + (0.0 if default_corridor else rng.uniform(-0.9, 0.9))
    camera_height = cam_h_map.get(terrain, 17.5) + (
        0.0 if default_corridor else rng.uniform(-0.6, 0.6)
    )

    haze_max = 0.72 if palette_name in ("synthwave", "volcanic", "moonlight") else 0.78
    shimmer_strength = (
        0.0
        if (is_lava or palette_name == "mars" or terrain in ("dunes", "canyon"))
        else (0.25 if terrain in ("archipelago", "coast") else 0.20)
    )

    return _SceneParams(
        seed=seed,
        palette_name=palette_name,
        terrain=terrain,
        sway_a=sway_a,
        sway_b=sway_b,
        sway_phase=sway_phase,
        horizon=horizon,
        camera_height=camera_height,
        sun_x=sun_x,
        sun_y=sun_y,
        sun_r=sun_r,
        celestial=celestial,
        has_aurora=has_aurora,
        has_stars=has_stars,
        has_clouds=has_clouds,
        haze_max=haze_max,
        shimmer_strength=shimmer_strength,
        is_lava=is_lava,
        has_water_channel=has_water_channel,
        coast_side=coast_side,
    )


def _channel_center(z: float, sway_a: float, sway_b: float, sway_phase: float) -> float:
    t = math.tau * z / MAP_SIZE + sway_phase
    return 64.0 + sway_a * math.sin(t) + sway_b * math.sin(2.0 * t)


def _periodic_fbm_grid(
    seed: int,
    base_period: int = 4,
    octaves: int = 4,
    persistence: float = 0.5,
) -> list[list[float]]:
    """Generate a C2-smooth toroidal fBm grid in [0, 1] of size MAP_SIZE x MAP_SIZE."""
    rng = random.Random(seed)
    acc = [[0.0] * MAP_SIZE for _ in range(MAP_SIZE)]
    amp = 1.0
    amp_sum = 0.0
    period = base_period

    for _ in range(octaves):
        table = [rng.random() for _ in range(period * period)]
        idx0 = [0] * MAP_SIZE
        idx1 = [0] * MAP_SIZE
        fade = [0.0] * MAP_SIZE
        scale = period / MAP_SIZE
        for i in range(MAP_SIZE):
            v = i * scale
            i0 = int(v)
            f = v - i0
            idx0[i] = i0 % period
            idx1[i] = (i0 + 1) % period
            fade[i] = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)

        for z in range(MAP_SIZE):
            rz0 = idx0[z] * period
            rz1 = idx1[z] * period
            fz = fade[z]
            inv_fz = 1.0 - fz
            row = acc[z]
            for x in range(MAP_SIZE):
                x0 = idx0[x]
                x1 = idx1[x]
                fx = fade[x]
                n0 = table[rz0 + x0] + (table[rz0 + x1] - table[rz0 + x0]) * fx
                n1 = table[rz1 + x0] + (table[rz1 + x1] - table[rz1 + x0]) * fx
                row[x] += (n0 * inv_fz + n1 * fz) * amp

        amp_sum += amp
        amp *= persistence
        period = min(32, period * 2)

    inv_sum = 1.0 / amp_sum
    for z in range(MAP_SIZE):
        row = acc[z]
        for x in range(MAP_SIZE):
            row[x] *= inv_sum
    return acc


def _ridged(val: float, sharpness: float = 1.6) -> float:
    """Smoothly sharpened ridge value in [0, 1] without a Nyquist-breaking kink."""
    d = 2.0 * val - 1.0
    r = max(0.0, 1.0 - math.sqrt(d * d + 0.006))
    return r ** sharpness


def _pick_scenic_x_shift(heights: list[list[float]], scene: _SceneParams) -> int:
    """Choose a circular X shift so an unbroken mountain field aligns with a scenic alpine pass."""
    best_shift = 0
    best_score = float("inf")
    path_cx = [
        int(round(_channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase))) & 127
        for z in range(MAP_SIZE)
    ]
    for shift in range(0, MAP_SIZE, 2):
        path_samples: list[float] = []
        surround_samples: list[float] = []
        for z in range(0, MAP_SIZE, 2):
            row = heights[z]
            cx = (path_cx[z] + shift) & 127
            local_max = 0.0
            for dx in (-3, -1, 0, 1, 3):
                h = row[(cx + dx) & 127]
                if h > local_max:
                    local_max = h
            path_samples.append(local_max)
            for dx in (-26, -15, 15, 26):
                surround_samples.append(row[(cx + dx) & 127])
        path_samples.sort()
        surround_samples.sort()
        path_max = path_samples[-1]
        path_p90 = path_samples[int(len(path_samples) * 0.90)]
        path_med = path_samples[len(path_samples) // 2]
        surround_p92 = surround_samples[int(len(surround_samples) * 0.92)]
        score = 0.55 * path_max + 0.65 * path_p90 + 0.35 * path_med - 0.55 * surround_p92
        if score < best_score:
            best_score = score
            best_shift = shift
    return best_shift


def _place_asymmetric_features(
    rng: random.Random,
    scene: _SceneParams,
    specs: list[tuple[float, float, float]],
    *,
    clearance_pad: float,
) -> list[tuple[float, float, float, float, float, float, float]]:
    """Place toroidal asymmetric elliptical features (mesas/islands) clear of the camera lens."""
    count = len(specs)
    features: list[tuple[float, float, float, float, float, float, float]] = []
    # Randomize left/right side sequence while avoiding symmetrical paired walls
    sides = [(-1 if i % 2 == 0 else 1) for i in range(count)]
    rng.shuffle(sides)
    for i, (rx, rz, mh) in enumerate(specs):
        mz = ((i + rng.uniform(0.15, 0.85)) * MAP_SIZE / count) % MAP_SIZE
        side = sides[i]
        # Mix dramatic asymmetric passes, mid-field landmarks, and distant horizon silhouettes
        tier = i % 3
        if tier == 0:
            offset = rx * 0.96 + rng.uniform(clearance_pad, clearance_pad + 4.0)
        elif tier == 1:
            offset = rx * 0.98 + rng.uniform(clearance_pad + 7.5, clearance_pad + 16.5)
        else:
            offset = rx * 0.92 + rng.uniform(clearance_pad + 18.0, 44.0)
        ch_at_z = _channel_center(mz, scene.sway_a, scene.sway_b, scene.sway_phase)
        mx = (ch_at_z + side * offset) % MAP_SIZE

        # Guarantee the feature does not clip the curving flight path anywhere along its Z span
        for dz_check in range(-int(rz) - 3, int(rz) + 4, 2):
            zz = (mz + dz_check) % MAP_SIZE
            ch_z = _channel_center(zz, scene.sway_a, scene.sway_b, scene.sway_phase)
            dx_signed = (mx - ch_z + 64.0) % MAP_SIZE - 64.0
            min_dist = rx * 0.94 + clearance_pad
            if abs(dx_signed) < min_dist:
                push = min_dist - abs(dx_signed) + 0.5
                mx = (mx + side * push) % MAP_SIZE

        ang = rng.uniform(0.0, math.tau)
        features.append((mx, mz, rx, rz, mh, math.cos(ang), math.sin(ang)))
    return features


def _generate_heights(scene: _SceneParams) -> list[list[float]]:
    """Build a toroidal heightfield for the selected terrain archetype."""
    n1 = _periodic_fbm_grid(scene.seed * 7 + 11, base_period=6, octaves=4, persistence=0.52)
    n2 = _periodic_fbm_grid(scene.seed * 13 + 37, base_period=8, octaves=3, persistence=0.50)
    n3 = _periodic_fbm_grid(scene.seed * 29 + 73, base_period=4, octaves=3, persistence=0.48)

    terrain = scene.terrain
    rng = random.Random(scene.seed * 919 + 41)
    heights: list[list[float]] = []

    if terrain == "fjord":
        # The sole classic carved valley / lava river / fjord corridor
        channel_w = rng.uniform(6.4, 8.2)
        wall_w = rng.uniform(14.0, 18.0)
        for z in range(MAP_SIZE):
            ch = _channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase)
            r1_row, r2_row, r3_row = n1[z], n2[z], n3[z]
            row = [0.0] * MAP_SIZE
            for x in range(MAP_SIZE):
                dist = abs((x - ch + 64.0) % MAP_SIZE - 64.0)
                valley = _smoothstep(channel_w, channel_w + wall_w, dist)
                ridge = 0.62 * _ridged(r1_row[x], 1.85) + 0.38 * _ridged(r2_row[x], 1.75)
                mass = 0.25 + 0.75 * r3_row[x]
                row[x] = _WATER_LEVEL + (2.6 + 29.0 * ridge * mass) * valley
            heights.append(row)

    elif terrain == "peaks":
        # Open unbroken alpine flyover — zero carved center corridor or road!
        # Use broader base periods so sweeping alpine mountain chains read cleanly without
        # near-field spiky flicker.
        p1 = _periodic_fbm_grid(scene.seed * 7 + 11, base_period=4, octaves=4, persistence=0.50)
        p2 = _periodic_fbm_grid(scene.seed * 13 + 37, base_period=6, octaves=3, persistence=0.48)
        kx = rng.choice((1, 2)) * rng.choice((-1, 1))
        kz = rng.choice((1, 2))
        has_tarns = scene.palette_name not in ("desert", "mars")
        for z in range(MAP_SIZE):
            r1_row, r2_row, r3_row = p1[z], p2[z], n3[z]
            row = [0.0] * MAP_SIZE
            for x in range(MAP_SIZE):
                chain = 0.5 + 0.5 * math.sin(
                    math.tau * (kx * x + kz * z) / MAP_SIZE + 2.8 * (r3_row[x] - 0.5)
                )
                macro = 0.56 * r3_row[x] + 0.44 * chain
                r_main = _ridged(r1_row[x], 1.95)
                r_sec = _ridged(r2_row[x], 1.65)
                spire = 0.66 * r_main + 0.34 * r_sec
                if has_tarns:
                    # Scattered natural high-alpine tarns in deep 2D basins (never a center strip)
                    basin = _smoothstep(0.15, 0.26, macro * 0.72 + spire * 0.28)
                    row[x] = _WATER_LEVEL + (2.6 + 26.5 * spire * (0.26 + 0.74 * macro)) * basin
                else:
                    row[x] = 3.8 + 25.0 * spire * (0.26 + 0.74 * macro)
            heights.append(row)
        # Rotate untouched torus in X so the flight line naturally glides over scenic alpine passes
        shift = _pick_scenic_x_shift(heights, scene)
        if shift:
            heights = [row[shift:] + row[:shift] for row in heights]

    elif terrain == "canyon":
        # Monument Valley / Mars basin: wide open dry plain + scattered asymmetric terraced mesas
        step_h = rng.uniform(4.2, 5.0)
        specs: list[tuple[float, float, float]] = []
        # 3 grand stepped plateaus
        for _ in range(3):
            specs.append((rng.uniform(11.0, 15.0), rng.uniform(9.5, 14.0), rng.uniform(16.0, 20.5)))
        # 4 medium flat-topped mesas
        for _ in range(4):
            specs.append((rng.uniform(6.8, 9.8), rng.uniform(6.2, 9.2), rng.uniform(14.5, 19.5)))
        # 4 Monument Valley spires / buttes
        for _ in range(4):
            specs.append((rng.uniform(4.2, 5.8), rng.uniform(4.2, 5.8), rng.uniform(16.0, 20.5)))
        rng.shuffle(specs)
        mesas = _place_asymmetric_features(rng, scene, specs, clearance_pad=7.8)

        for z in range(MAP_SIZE):
            r1_row, r2_row, r3_row = n1[z], n2[z], n3[z]
            active_mesas = []
            for mx, mz, rx, rz, mh, rc, rs in mesas:
                dz = (z - mz + 64.0) % MAP_SIZE - 64.0
                if abs(dz) <= max(rx, rz) * 1.52:
                    active_mesas.append((mx, dz, rx, rz, mh, rc, rs))

            row = [0.0] * MAP_SIZE
            for x in range(MAP_SIZE):
                # Gently undulating dry desert basin floor with subtle sunlit washes
                floor_h = 4.2 + 2.4 * r2_row[x] + 1.8 * r3_row[x]
                mesa_h = 0.0
                for mx, dz, rx, rz, mh, rc, rs in active_mesas:
                    dx = (x - mx + 64.0) % MAP_SIZE - 64.0
                    if abs(dx) > max(rx, rz) * 1.52:
                        continue
                    rx_d = dx * rc + dz * rs
                    rz_d = -dx * rs + dz * rc
                    d = math.hypot(rx_d / rx, rz_d / rz)
                    d_w = d + 0.22 * (r1_row[x] - 0.5) + 0.14 * (r2_row[x] - 0.5)
                    if d_w < 1.28:
                        raw_m = mh * _smoothstep(1.26, 0.52, d_w)
                        u = raw_m / step_h
                        fl = math.floor(u)
                        fr = u - fl
                        terraced = (fl + _smoothstep(0.30, 0.70, fr)) * step_h
                        if terraced > mesa_h:
                            mesa_h = terraced
                row[x] = floor_h + mesa_h
            heights.append(row)

    elif terrain == "dunes":
        # Endless wind-sculpted desert — zero corridor, zero water, sweeping edge-to-edge waves!
        kx = rng.choice((2, 3)) * rng.choice((-1, 1))
        kz = rng.choice((2, 3))
        for z in range(MAP_SIZE):
            r1_row, r2_row, r3_row = n1[z], n2[z], n3[z]
            row = [0.0] * MAP_SIZE
            for x in range(MAP_SIZE):
                phi = (
                    math.tau * (kx * x + kz * z) / MAP_SIZE
                    + 2.4 * (r3_row[x] - 0.5)
                    + 0.80 * (r1_row[x] - 0.5)
                )
                # Asymmetric windward/slip-face dune profile without Nyquist kink
                skew = math.sin(phi + 0.48 * math.sin(phi))
                crest = 1.0 - math.sqrt((1.0 - (0.5 + 0.5 * skew)) ** 2 + 0.015)
                mega = 0.5 + 0.5 * math.sin(
                    math.tau * (x - z) / MAP_SIZE + 2.0 * (r2_row[x] - 0.5)
                )
                amp = 6.4 + 8.4 * (0.50 * r2_row[x] + 0.30 * r3_row[x] + 0.20 * mega)
                row[x] = 4.2 + 1.6 * r3_row[x] + amp * crest
            heights.append(row)

    elif terrain == "coast":
        # Dramatic one-sided coastline: open shimmering ocean on one side, towering cliffs on the other!
        side = scene.coast_side
        shore_offset = rng.uniform(5.2, 7.6)
        p1 = rng.uniform(0.0, math.tau)
        p2 = rng.uniform(0.0, math.tau)
        # Optional 1-2 small offshore sea stacks on the ocean side for extra coastal drama
        sea_stacks: list[tuple[float, float, float, float]] = []
        if rng.random() < 0.65:
            for _ in range(rng.randint(1, 2)):
                sz = rng.uniform(0.0, MAP_SIZE)
                ch_s = _channel_center(sz, scene.sway_a, scene.sway_b, scene.sway_phase)
                sx = (ch_s - side * rng.uniform(18.0, 30.0)) % MAP_SIZE
                sea_stacks.append((sx, sz, rng.uniform(3.2, 4.5), rng.uniform(6.5, 11.0)))

        for z in range(MAP_SIZE):
            ch = _channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase)
            t = math.tau * z / MAP_SIZE
            headland = 4.6 * math.sin(2.0 * t + p1) + 2.4 * math.sin(3.0 * t + p2)
            # Keep shore curving organically without intruding directly under the camera lens
            shore_dist = max(3.6, shore_offset + headland)
            shore_base = ch + side * shore_dist
            headland_mass = 0.72 + 0.28 * math.sin(2.0 * t + p1 + 0.6)
            r1_row, r2_row, r3_row = n1[z], n2[z], n3[z]
            row = [0.0] * MAP_SIZE
            for x in range(MAP_SIZE):
                # Signed distance inland from camera (positive = land side, negative = ocean side)
                raw_u = ((x - ch + 64.0) % MAP_SIZE - 64.0) * side
                # Taper back edge of the torus cleanly to ocean so no wraparound peaks appear at sea
                back_fade = 1.0 - _smoothstep(44.0, 53.5, raw_u)
                u = ((x - shore_base + 64.0) % MAP_SIZE - 64.0) * side
                u_wobble = u + 4.4 * (r3_row[x] - 0.5) + 2.0 * (r1_row[x] - 0.5)
                h = _WATER_LEVEL
                if u_wobble > 0.0 and back_fade > 0.0:
                    cliff = _smoothstep(0.0, 12.0, u_wobble)
                    inland = _smoothstep(0.0, 26.0, u_wobble)
                    ridge = 0.60 * _ridged(r1_row[x], 1.95) + 0.40 * _ridged(r2_row[x], 1.80)
                    mass = (0.35 + 0.65 * r3_row[x]) * headland_mass
                    h = (
                        _WATER_LEVEL
                        + (2.4 + (10.5 + 23.0 * ridge * mass) * (0.42 + 0.58 * inland))
                        * cliff
                        * back_fade
                    )
                for sx, sz, sr, sh in sea_stacks:
                    dz = (z - sz + 64.0) % MAP_SIZE - 64.0
                    if abs(dz) <= sr * 1.5:
                        dx = (x - sx + 64.0) % MAP_SIZE - 64.0
                        if abs(dx) <= sr * 1.5:
                            d_st = math.hypot(dx, dz) / sr + 0.25 * (r2_row[x] - 0.5)
                            if d_st < 1.15:
                                stack_h = _WATER_LEVEL + sh * _smoothstep(1.12, 0.24, d_st)
                                if stack_h > h:
                                    h = stack_h
                row[x] = h
            heights.append(row)

    else:  # archipelago
        # Wide open shimmering ocean + asymmetric scattered volcanic/lush islands (no corridor!)
        specs = []
        # 3 dramatic volcanic peak islands
        for _ in range(3):
            specs.append((rng.uniform(10.0, 14.0), rng.uniform(9.0, 13.5), rng.uniform(18.5, 25.0)))
        # 4 medium lush islands
        for _ in range(4):
            specs.append((rng.uniform(6.8, 10.0), rng.uniform(6.2, 9.6), rng.uniform(11.0, 17.5)))
        # 3 small rocky islets / sandy cays
        for _ in range(3):
            specs.append((rng.uniform(4.0, 6.4), rng.uniform(4.0, 6.2), rng.uniform(5.5, 11.0)))
        rng.shuffle(specs)
        islands = _place_asymmetric_features(rng, scene, specs, clearance_pad=8.8)

        for z in range(MAP_SIZE):
            r1_row, r2_row, r3_row = n1[z], n2[z], n3[z]
            active_islands = []
            for ix, iz, rx, rz, ih, rc, rs in islands:
                dz = (z - iz + 64.0) % MAP_SIZE - 64.0
                if abs(dz) <= max(rx, rz) * 1.52:
                    active_islands.append((ix, dz, rx, rz, ih, rc, rs))

            row = [_WATER_LEVEL] * MAP_SIZE
            for x in range(MAP_SIZE):
                best_h = _WATER_LEVEL
                for ix, dz, rx, rz, ih, rc, rs in active_islands:
                    dx = (x - ix + 64.0) % MAP_SIZE - 64.0
                    if abs(dx) > max(rx, rz) * 1.52:
                        continue
                    rx_d = dx * rc + dz * rs
                    rz_d = -dx * rs + dz * rc
                    d = math.hypot(rx_d / rx, rz_d / rz)
                    d_w = d + 0.26 * (r1_row[x] - 0.5) + 0.16 * (r3_row[x] - 0.5)
                    if d_w < 1.22:
                        shape = _smoothstep(1.20, 0.26, d_w)
                        peak = 0.56 + 0.44 * _ridged(r2_row[x], 1.55)
                        h = _WATER_LEVEL + ih * shape * peak
                        if h > best_h:
                            best_h = h
                row[x] = best_h
            heights.append(row)

    return heights


def _elevation_color(
    height: float, stops: list[tuple[float, tuple[float, float, float]]]
) -> tuple[float, float, float]:
    if height <= stops[0][0]:
        return stops[0][1]
    for i in range(len(stops) - 1):
        h0, c0 = stops[i]
        h1, c1 = stops[i + 1]
        if height <= h1:
            t = (height - h0) / (h1 - h0)
            return _blend_f(c0, c1, t)
    return stops[-1][1]


def _colorize_terrain(
    heights: list[list[float]], palette: dict, scene: _SceneParams
) -> list[list[tuple[int, int, int]]]:
    """Shade heightfield with calibrated elevation bands and directional LED-tuned lighting."""
    land_heights = sorted(h for row in heights for h in row if h > 3.6)
    if land_heights:
        h_high = land_heights[int(len(land_heights) * 0.96)]
        h_peak = max(13.5, min(28.0, h_high))
    else:
        h_peak = 18.0

    water = _rgb_f(palette["water"])
    shore = _rgb_f(palette["shore"])
    land = [_rgb_f(c) for c in palette["land"]]
    warm = _rgb_f(palette.get("highlight", "#ffe2b8"))
    cool = _rgb_f(palette.get("shadow", "#101228"))
    lava_core = _rgb_f(palette["lava_core"]) if palette.get("lava_core") else None
    neon_crest = _rgb_f(palette["neon_crest"]) if palette.get("neon_crest") else None

    span = max(9.0, h_peak - 3.6)
    stops = [
        (2.15, water),
        (3.10, shore),
        (4.10, land[0]),
        (4.10 + span * 0.36, land[1]),
        (4.10 + span * 0.72, land[2]),
        (4.10 + span * 0.96, land[3]),
    ]

    # Align directional sunlight with the celestial body's azimuth for dramatic 3D contrast
    sun_dx = (scene.sun_x - 32.0) / 32.0
    lx = 0.72 if abs(sun_dx) < 0.2 else (1.0 if sun_dx > 0 else -1.0) * min(1.0, 0.55 + abs(sun_dx))
    is_canyon = scene.terrain == "canyon"
    is_dunes = scene.terrain == "dunes"
    max_warm = 0.24 if lava_core is not None else (0.34 if is_dunes else 0.30)

    # Optional subtle periodic noise for volcanic magma variation
    magma_noise = (
        _periodic_fbm_grid(scene.seed * 41 + 7, base_period=6, octaves=2, persistence=0.5)
        if lava_core is not None
        else None
    )

    colors: list[list[tuple[int, int, int]]] = []
    for z in range(MAP_SIZE):
        zm = (z - 1) & 127
        zp = (z + 1) & 127
        hz = heights[z]
        hm = heights[zm]
        hp = heights[zp]
        color_row: list[tuple[int, int, int]] = []
        for x in range(MAP_SIZE):
            h = hz[x]
            if lava_core is not None and h <= 2.35 and magma_noise is not None:
                # Glowing molten lava channel with hotter core currents
                mv = _smoothstep(0.30, 0.76, magma_noise[z][x])
                col = _blend_f(water, lava_core, mv * 0.72)
                color_row.append((round(col[0]), round(col[1]), round(col[2])))
                continue

            col = _elevation_color(h, stops)

            # Horizontal geological rock strata bands on canyon mesa walls
            if is_canyon and h > 5.2:
                strata_mask = _smoothstep(5.2, 8.8, h)
                strata = 0.5 + 0.5 * math.sin(h * 1.65)
                if strata > 0.5:
                    col = _blend_f(col, land[2], (strata - 0.5) * 0.34 * strata_mask)
                else:
                    col = _blend_f(col, land[0], (0.5 - strata) * 0.38 * strata_mask)

            if h > 2.35:
                xm = (x - 1) & 127
                xp = (x + 1) & 127
                land_mask = _smoothstep(2.35, 4.0, h)
                sx = 0.5 * (hz[xp] - hz[xm])
                sz = 0.5 * (hp[x] - hm[x])
                grad = math.hypot(sx, sz)
                norm = math.sqrt(1.0 + sx * sx + sz * sz)

                # Expose darker cliff rock on steep faces so snow/caps cling to summits & ridges
                if h > 4.10 + span * 0.55 and grad > 1.35 and not is_dunes and neon_crest is None:
                    rock_t = _clamp((grad - 1.35) * 0.32, 0.0, 0.45)
                    col = _blend_f(col, land[1], rock_t)

                # Positive when slope faces the sun, negative in shadow
                dot = (sx * (-lx) * 1.15 - sz * 0.35) / norm
                if is_dunes:
                    dot *= 1.35
                light = _clamp(dot * 0.54, -0.46, max_warm) * land_mask
                if light > 0.0:
                    col = _blend_f(col, warm, light)
                else:
                    col = _blend_f(col, cool, -light)

                # Subtle convex ridge crest accent (snow rim / synthwave neon ridge)
                lap = 4.0 * h - (hz[xm] + hz[xp] + hm[x] + hp[x])
                if lap > 0.14 and h > 6.5:
                    crest_t = _clamp((lap - 0.14) * 0.38, 0.0, 0.32)
                    if neon_crest is not None:
                        col = _blend_f(col, neon_crest, crest_t * 0.85)
                    elif lava_core is None:
                        col = _blend_f(col, land[3], crest_t * 0.48)

                # Volcanic upward ember bounce light on low obsidian walls right beside the lava
                if lava_core is not None and h < 6.8:
                    ember_t = (1.0 - _smoothstep(2.5, 6.8, h)) * 0.28
                    col = _blend_f(col, shore, ember_t)

            color_row.append(
                (
                    max(0, min(255, round(col[0]))),
                    max(0, min(255, round(col[1]))),
                    max(0, min(255, round(col[2]))),
                )
            )
        colors.append(color_row)
    return colors


def _terrain(
    seed: int,
    palette: dict,
    terrain: str | None = None,
    *,
    scene: _SceneParams | None = None,
) -> tuple[list, list]:
    """Build a toroidal height and color map for a seeded procedural world."""
    if scene is None:
        palette_name = _palette_name_for(palette)
        terrain_name = _resolve_terrain_name(terrain, seed, palette_name)
        scene = _build_scene(seed, palette_name, terrain_name, default_corridor=True)
    heights = _generate_heights(scene)
    colors = _colorize_terrain(heights, palette, scene)
    return heights, colors


def _downsample_scalar(grid: list[list[float]]) -> list[list[float]]:
    half = len(grid) // 2
    out: list[list[float]] = []
    for z in range(half):
        r0 = grid[z * 2]
        r1 = grid[z * 2 + 1]
        out.append(
            [
                0.25 * (r0[x * 2] + r0[x * 2 + 1] + r1[x * 2] + r1[x * 2 + 1])
                for x in range(half)
            ]
        )
    return out


def _downsample_rgb(
    grid: list[list[tuple[int, int, int]]],
) -> list[list[tuple[int, int, int]]]:
    half = len(grid) // 2
    out: list[list[tuple[int, int, int]]] = []
    for z in range(half):
        r0 = grid[z * 2]
        r1 = grid[z * 2 + 1]
        row: list[tuple[int, int, int]] = []
        for x in range(half):
            c00, c01 = r0[x * 2], r0[x * 2 + 1]
            c10, c11 = r1[x * 2], r1[x * 2 + 1]
            row.append(
                (
                    (c00[0] + c01[0] + c10[0] + c11[0] + 2) >> 2,
                    (c00[1] + c01[1] + c10[1] + c11[1] + 2) >> 2,
                    (c00[2] + c01[2] + c10[2] + c11[2] + 2) >> 2,
                )
            )
        out.append(row)
    return out


def _prepare_mips(
    heights: list[list[float]], colors: list[list[tuple[int, int, int]]]
) -> tuple[list[list[list[float]]], list[list[list[tuple[int, int, int]]]]]:
    h1 = _downsample_scalar(heights)
    h2 = _downsample_scalar(h1)
    c1 = _downsample_rgb(colors)
    c2 = _downsample_rgb(c1)
    return [heights, h1, h2], [colors, c1, c2]


def _safe_camera_height(heights: list[list[float]], scene: _SceneParams) -> float:
    """Ensure a constant-altitude flight path always clears the underlying terrain smoothly."""
    max_under = 0.0
    for z in range(MAP_SIZE):
        cx = int(round(_channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase))) & 127
        for dx in (-2, -1, 0, 1, 2):
            h = heights[z][(cx + dx) & 127]
            if h > max_under:
                max_under = h
    return max(scene.camera_height, max_under + 4.8)


def _camera_altitude_profile(
    heights: list[list[float]], scene: _SceneParams
) -> tuple[float, tuple[tuple[float, float], ...]]:
    """Compute a strictly periodic, C-infinity smooth Fourier camera altitude curve."""
    if scene.terrain not in ("peaks", "dunes"):
        return (_safe_camera_height(heights, scene), ())

    # 1. Measure required near-field clearance at every z along the flight path
    base_margin = 9.0 if scene.terrain == "peaks" else 6.8
    req = [scene.camera_height] * MAP_SIZE
    for z in range(MAP_SIZE):
        need = scene.camera_height
        for dz in range(0, 9):
            zz = (z + dz) & 127
            cx = (
                int(round(_channel_center(z + dz, scene.sway_a, scene.sway_b, scene.sway_phase)))
                & 127
            )
            half_w = 2 if dz <= 2 else (4 if dz <= 5 else 5)
            margin = base_margin if dz <= 3 else max(3.2, base_margin - (dz - 3) * 0.65)
            row = heights[zz]
            for dx in range(-half_w, half_w + 1):
                cand = row[(cx + dx) & 127] + margin
                if cand > need:
                    need = cand
        req[z] = need

    # 2. Gentle periodic upper-envelope dilation so the camera glides smoothly ahead of ridges
    env = [0.0] * MAP_SIZE
    for z in range(MAP_SIZE):
        best = req[z]
        for d in range(-14, 15):
            cand = req[(z + d) & 127] - 0.035 * d * d
            if cand > best:
                best = cand
        env[z] = best

    # 3. Project onto ultra-smooth low-frequency Fourier harmonics (k=1..2) with gentle
    # amplitude damping so vertical altitude glides smoothly without foreground vertical bobbing.
    inv_n = 1.0 / MAP_SIZE
    a0 = sum(env) * inv_n
    harmonics: list[tuple[float, float]] = []
    damp_by_k = (0.45, 0.22)
    for k in range(1, 3):
        ak = 0.0
        bk = 0.0
        step = math.tau * k * inv_n
        for z in range(MAP_SIZE):
            ang = z * step
            ak += env[z] * math.cos(ang)
            bk += env[z] * math.sin(ang)
        damp = damp_by_k[k - 1]
        harmonics.append((2.0 * ak * inv_n * damp, 2.0 * bk * inv_n * damp))

    # 4. Lift DC offset just enough to guarantee zero terrain collision anywhere in the loop
    max_deficit = 0.0
    for z in range(MAP_SIZE):
        theta = math.tau * z * inv_n
        val = a0
        for k, (ak, bk) in enumerate(harmonics, start=1):
            ang = k * theta
            val += ak * math.cos(ang) + bk * math.sin(ang)
        deficit = req[z] - val
        if deficit > max_deficit:
            max_deficit = deficit

    return (a0 + max_deficit, tuple(harmonics))


def _camera_height_at(
    profile: tuple[float, tuple[tuple[float, float], ...]], phase: float
) -> float:
    """Evaluate a periodic camera altitude profile at phase in [0, 1)."""
    a0, harmonics = profile
    if not harmonics:
        return a0
    theta = math.tau * (phase % 1.0)
    h = a0
    for k, (ak, bk) in enumerate(harmonics, start=1):
        ang = k * theta
        h += ak * math.cos(ang) + bk * math.sin(ang)
    return h


class _SkyRenderer:
    """Precomputed static sky + smooth periodic celestial/aurora/cloud overlays."""

    def __init__(self, palette: dict, scene: _SceneParams) -> None:
        self.scene = scene
        self.sky_top = _rgb_f(palette["sky"][0])
        self.sky_bottom = _rgb_f(palette["sky"][1])
        self.sky_mid = (
            _rgb_f(palette["sky_mid"])
            if palette.get("sky_mid")
            else _blend_f(self.sky_top, self.sky_bottom, 0.45)
        )
        self.sun_rgb = _rgb_f(palette["sun"])
        self.haze_rgb = (
            round(self.sky_bottom[0]),
            round(self.sky_bottom[1]),
            round(self.sky_bottom[2]),
        )
        self.shimmer_rgb = _rgb_f(palette.get("shimmer", palette["sun"]))
        self.lava_core = _rgb_f(palette["lava_core"]) if palette.get("lava_core") else None

        aurora_hex = palette.get("aurora")
        if aurora_hex:
            self.aurora_colors = tuple(_rgb_f(c) for c in aurora_hex)
        else:
            self.aurora_colors = (_rgb_f("#24ffa8"), _rgb_f("#36d8ff"), _rgb_f("#9e6cff"))

        # Precompute base static sky + celestial disc (64 x 64 RGB float list)
        self.base_sky = self._build_base_sky()
        self.base_sky_int = [
            (round(c[0]), round(c[1]), round(c[2])) for c in self.base_sky
        ]

        # Precompute deterministic starfield (smooth sine breathing, never flickers)
        rng = random.Random(scene.seed * 613 + 19)
        self.stars: list[tuple[int, int, float, float, tuple[float, float, float]]] = []
        if scene.has_stars:
            star_count = rng.randint(14, 22)
            for _ in range(star_count):
                sx = rng.randint(1, 62)
                sy = rng.randint(1, 20)
                dist_sun = math.hypot(sx - scene.sun_x, sy - scene.sun_y)
                if dist_sun < scene.sun_r + 3.0:
                    continue
                tint = _blend_f((235.0, 242.0, 255.0), self.sun_rgb, rng.uniform(0.0, 0.35))
                self.stars.append((sx, sy, rng.uniform(0.35, 0.85), rng.uniform(0.0, math.tau), tint))

        # Precompute gentle drifting cloud ribbons (strictly periodic over phase)
        self.clouds: list[tuple[float, float, float, float, float, float]] = []
        if scene.has_clouds:
            cloud_count = rng.randint(2, 4)
            for _ in range(cloud_count):
                cy = rng.uniform(7.0, 21.0)
                cx0 = rng.uniform(0.0, 64.0)
                rx = rng.uniform(7.0, 14.0)
                ry = rng.uniform(1.4, 2.6)
                opacity = rng.uniform(0.14, 0.26)
                speed = rng.choice((1.0, 1.0, 2.0))
                self.clouds.append((cx0, cy, rx, ry, opacity, speed))
        self.cloud_tint = _blend_f(self.sky_bottom, self.sun_rgb, 0.55)
        self.aurora_phase_offset = rng.uniform(0.0, math.tau)
        self.dynamic = bool(self.stars or self.clouds or scene.has_aurora)

    def _build_base_sky(self) -> list[tuple[float, float, float]]:
        s = self.scene
        pixels: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * (64 * 64)
        horizon_y = max(24.0, s.horizon + 4.0)

        for y in range(64):
            t = _clamp(y / horizon_y)
            if t < 0.52:
                u = t / 0.52
                row_col = _blend_f(self.sky_top, self.sky_mid, u * u * (3.0 - 2.0 * u))
            else:
                u = (t - 0.52) / 0.48
                row_col = _blend_f(self.sky_mid, self.sky_bottom, u * u * (3.0 - 2.0 * u))

            for x in range(64):
                col = row_col
                # Subtle warm/tinted radial glow around the sun/moon
                dx = x + 0.5 - s.sun_x
                dy = y + 0.5 - s.sun_y
                dist = math.hypot(dx, dy)
                halo_r = s.sun_r * 3.1
                if dist < halo_r:
                    halo = (1.0 - dist / halo_r) ** 2.2
                    halo_str = 0.46 if s.celestial == "synth_sun" else 0.30
                    col = _blend_f(col, self.sun_rgb, halo * halo_str)

                # Draw celestial body with smooth sub-pixel anti-aliasing
                col = self._paint_celestial(col, x + 0.5, y + 0.5, dx, dy, dist)
                pixels[y * 64 + x] = col
        return pixels

    def _paint_celestial(
        self,
        col: tuple[float, float, float],
        px: float,
        py: float,
        dx: float,
        dy: float,
        dist: float,
    ) -> tuple[float, float, float]:
        s = self.scene
        r = s.sun_r
        kind = s.celestial

        if kind == "synth_sun":
            edge = _clamp(r + 0.55 - dist, 0.0, 1.0)
            if edge > 0.0:
                # Iconic vertical outrun gradient (bright yellow -> tangerine -> hot magenta)
                vt = _clamp((dy + r) / (2.0 * r))
                if vt < 0.5:
                    disc = _blend_f((255.0, 240.0, 96.0), (255.0, 134.0, 62.0), vt * 2.0)
                else:
                    disc = _blend_f((255.0, 134.0, 62.0), (255.0, 42.0, 136.0), (vt - 0.5) * 2.0)
                # Clean horizontal slices on lower half
                slice_mask = 1.0
                if vt > 0.46:
                    band = (py - (s.sun_y - 0.4)) % 2.6
                    gap_w = 0.42 + (vt - 0.46) * 1.35
                    if band < gap_w:
                        slice_mask = 0.0
                    elif band < gap_w + 0.35:
                        slice_mask = (band - gap_w) / 0.35
                col = _blend_f(col, disc, edge * slice_mask)
            return col

        if kind == "crescent":
            edge = _clamp(r + 0.5 - dist, 0.0, 1.0)
            if edge > 0.0:
                # Offset shadow disc carves a crisp crescent
                cut_x = s.sun_x + r * 0.42
                cut_y = s.sun_y - r * 0.24
                cut_d = math.hypot(px - cut_x, py - cut_y)
                cut_mask = _clamp(cut_d - (r * 0.88 - 0.45), 0.0, 1.0)
                # Faint earthshine inside the shadowed side looks magical on LEDs
                col = _blend_f(col, self.sun_rgb, edge * (0.12 + 0.88 * cut_mask))
            return col

        if kind == "twin_moons":
            edge1 = _clamp(r + 0.5 - dist, 0.0, 1.0)
            if edge1 > 0.0:
                shade = _clamp(0.68 - 0.35 * (dx / max(1.0, r)) - 0.25 * (dy / max(1.0, r)), 0.35, 1.0)
                disc = _blend_f(self.sky_mid, self.sun_rgb, shade)
                col = _blend_f(col, disc, edge1)
            # Second smaller companion moon offset across the sky
            m2x = s.sun_x + (-11.5 if s.sun_x > 32 else 11.5)
            m2y = s.sun_y - 2.6
            r2 = max(2.2, r * 0.46)
            d2 = math.hypot(px - m2x, py - m2y)
            edge2 = _clamp(r2 + 0.5 - d2, 0.0, 1.0)
            if edge2 > 0.0:
                tint2 = _blend_f(self.sun_rgb, self.sky_bottom, 0.25)
                col = _blend_f(col, tint2, edge2 * 0.92)
            return col

        if kind == "ringed":
            # Inclined elliptical ring (back half behind planet, front half in front)
            ang = -0.34
            ca, sa = math.cos(ang), math.sin(ang)
            rx = dx * ca - dy * sa
            ry = dx * sa + dy * ca
            ring_d = math.hypot(rx / (r * 2.15), ry / (r * 0.55))
            in_ring = 1.0 - _clamp(abs(ring_d - 0.88) / 0.16, 0.0, 1.0)
            ring_col = _blend_f(self.sun_rgb, (255.0, 232.0, 210.0), 0.35)

            if in_ring > 0.0 and ry < 0.0:
                col = _blend_f(col, ring_col, in_ring * 0.72)

            edge = _clamp(r + 0.5 - dist, 0.0, 1.0)
            if edge > 0.0:
                # Soft gas-giant bands + spherical shading
                band = 0.5 + 0.5 * math.sin(ry * 1.15)
                body = _blend_f(self.sun_rgb, self.sky_bottom, 0.15 + 0.25 * band)
                lit = _clamp(0.75 - 0.38 * (dx / max(1.0, r)) - 0.22 * (dy / max(1.0, r)), 0.28, 1.0)
                body = _blend_f(self.sky_top, body, lit)
                col = _blend_f(col, body, edge)

            if in_ring > 0.0 and ry >= 0.0:
                col = _blend_f(col, ring_col, in_ring * 0.85)
            return col

        if kind == "aurora_stars":
            # Small luminous polar moon peeking above the aurora
            edge = _clamp(r * 0.78 + 0.5 - dist, 0.0, 1.0)
            if edge > 0.0:
                cut_d = math.hypot(px - (s.sun_x + r * 0.32), py - (s.sun_y - r * 0.16))
                cut = _clamp(cut_d - (r * 0.68 - 0.4), 0.0, 1.0)
                col = _blend_f(col, self.sun_rgb, edge * (0.15 + 0.85 * cut))
            return col

        if kind == "ember_sun":
            edge = _clamp(r + 0.5 - dist, 0.0, 1.0)
            if edge > 0.0:
                core = _blend_f(self.sun_rgb, (255.0, 224.0, 128.0), _clamp(1.0 - dist / max(1.0, r)))
                col = _blend_f(col, core, edge)
            return col

        # Default: sun_glow
        edge = _clamp(r + 0.5 - dist, 0.0, 1.0)
        if edge > 0.0:
            core = _blend_f(self.sun_rgb, (255.0, 252.0, 236.0), _clamp(1.0 - dist / max(1.0, r)) * 0.55)
            col = _blend_f(col, core, edge)
        return col

    def pixels_for_phase(self, phase: float) -> list[tuple[int, int, int]]:
        """Return 64x64 sky pixels for a periodic phase in [0, 1)."""
        if not self.dynamic:
            return self.base_sky_int

        tau_p = math.tau * phase
        # Copy base sky (only y < 34 can ever be visible above terrain)
        out = list(self.base_sky_int)
        base = self.base_sky

        # 1. Smoothly undulating aurora ribbons (strictly periodic in phase)
        if self.scene.has_aurora:
            c0, c1, c2 = self.aurora_colors
            phi0 = self.aurora_phase_offset
            for x in range(64):
                nx = x * 0.085
                y_curtain1 = 9.5 + 2.1 * math.sin(nx + tau_p + phi0) + 0.9 * math.sin(2.0 * nx - tau_p)
                y_curtain2 = 13.5 + 1.6 * math.sin(nx * 1.2 - tau_p + 1.7)
                shimmer_x = 0.76 + 0.24 * math.sin(x * 0.16 + tau_p + phi0)
                tint_t = 0.5 + 0.5 * math.sin(x * 0.09 - tau_p)
                ribbon_rgb = _blend_f(c0, c1, tint_t)
                for y in range(1, 21):
                    # Curtain 1: bright bottom edge fading softly upward
                    d1 = y - y_curtain1
                    a1 = math.exp(-(d1 * d1) / (13.0 if d1 < 0 else 4.0)) * 0.52 * shimmer_x
                    # Curtain 2: secondary emerald/cyan veil
                    d2 = y - y_curtain2
                    a2 = math.exp(-(d2 * d2) / (9.5 if d2 < 0 else 3.2)) * 0.34
                    alpha = min(0.72, a1 + a2)
                    if alpha > 0.025:
                        top_t = _clamp(-d1 / 6.5)
                        a_col = _blend_f(ribbon_rgb, c2, top_t * 0.42)
                        idx = y * 64 + x
                        b_col = base[idx]
                        blended = _blend_f(b_col, a_col, alpha)
                        out[idx] = (round(blended[0]), round(blended[1]), round(blended[2]))

        # 2. Gentle drifting backlit cloud bands (wrapping modulo 64)
        if self.clouds:
            ct = self.cloud_tint
            for cx0, cy, rx, ry, opacity, speed in self.clouds:
                cx = (cx0 + phase * 64.0 * speed) % 64.0
                y_lo = max(1, int(cy - ry * 2.2))
                y_hi = min(28, int(cy + ry * 2.2) + 1)
                inv_rx = 1.0 / rx
                inv_ry = 1.0 / ry
                for y in range(y_lo, y_hi):
                    dy = (y + 0.5 - cy) * inv_ry
                    dy2 = dy * dy
                    if dy2 >= 4.0:
                        continue
                    row_off = y * 64
                    for x in range(64):
                        dx = ((x + 0.5 - cx + 32.0) % 64.0 - 32.0) * inv_rx
                        d2 = dx * dx + dy2
                        if d2 < 2.2:
                            w = math.exp(-d2 * 1.45) * opacity
                            idx = row_off + x
                            cur = out[idx]
                            out[idx] = (
                                round(cur[0] + (ct[0] - cur[0]) * w),
                                round(cur[1] + (ct[1] - cur[1]) * w),
                                round(cur[2] + (ct[2] - cur[2]) * w),
                            )

        # 3. Smoothly breathing stars (zero abrupt flicker)
        if self.stars:
            for sx, sy, amp, st_phase, tint in self.stars:
                brightness = amp * (0.76 + 0.24 * math.sin(tau_p + st_phase))
                idx = sy * 64 + sx
                cur = out[idx]
                out[idx] = (
                    round(cur[0] + (tint[0] - cur[0]) * brightness),
                    round(cur[1] + (tint[1] - cur[1]) * brightness),
                    round(cur[2] + (tint[2] - cur[2]) * brightness),
                )

        return out


def _render_frame(
    h_mips: list[list[list[float]]],
    c_mips: list[list[list[tuple[int, int, int]]]],
    sky: _SkyRenderer,
    scene: _SceneParams,
    camera_height: float,
    phase: float,
) -> Image.Image:
    """Draw depth slices with trilinear mip filtering and 2x horizontal supersampling."""
    phase %= 1.0
    camera_z = phase * MAP_SIZE
    camera_x = _channel_center(camera_z, scene.sway_a, scene.sway_b, scene.sway_phase)
    sky_pixels = sky.pixels_for_phase(phase)
    sb_r, sb_g, sb_b = sky.haze_rgb
    sh_r, sh_g, sh_b = sky.shimmer_rgb
    shimmer_str = scene.shimmer_strength
    is_lava = scene.is_lava
    lava_r, lava_g, lava_b = sky.lava_core if sky.lava_core is not None else (255.0, 224.0, 82.0)
    sun_x = scene.sun_x
    horizon = scene.horizon
    haze_max = scene.haze_max
    tau_phase = math.tau * phase

    # Flat column-major buffer for fast slice writes: col_buf[sx] has 64 RGB tuples
    col_buf = [
        [sky_pixels[y * 64 + (sx >> 1)] for y in range(64)]
        for sx in range(_SUB_W)
    ]
    # Exact sub-pixel vertical coverage state per sub-column (analytical edge AA)
    hidden_f = [64.0] * _SUB_W
    fr_y_arr = [64] * _SUB_W
    fr_r_arr = [0.0] * _SUB_W
    fr_g_arr = [0.0] * _SUB_W
    fr_b_arr = [0.0] * _SUB_W
    h0_grid, h1_grid, h2_grid = h_mips
    c0_grid, c1_grid, c2_grid = c_mips
    x_offsets = _X_OFFSETS

    for depth, c_lod, h_lod, haze_t in _DEPTH_SLICES:
        map_z = camera_z + depth
        inv_depth_scale = _PROJ_SCALE / depth
        haze = haze_max if haze_t > haze_max else haze_t
        one_minus_haze = 1.0 - haze
        haze_r = sb_r * haze
        haze_g = sb_g * haze
        haze_b = sb_b * haze

        # Choose mip levels for trilinear color & light far-distance height sampling
        if c_lod <= 0.0:
            c_lod0, c_lod1, c_frac, c_scale0, c_scale1, c_mask0, c_mask1 = (
                c0_grid, c0_grid, 0.0, 1.0, 1.0, 127, 127
            )
        elif c_lod < 1.0:
            c_lod0, c_lod1, c_frac, c_scale0, c_scale1, c_mask0, c_mask1 = (
                c0_grid, c1_grid, c_lod, 1.0, 0.5, 127, 63
            )
        else:
            f = 1.0 if c_lod >= 2.0 else (c_lod - 1.0)
            c_lod0, c_lod1, c_frac, c_scale0, c_scale1, c_mask0, c_mask1 = (
                c1_grid, c2_grid, f, 0.5, 0.25, 63, 31
            )

        # Keep near/mid mountain silhouettes razor-crisp; lightly mip heights only far away
        if h_lod <= 0.0:
            h_lod0, h_lod1, h_frac, h_scale0, h_scale1, h_mask0, h_mask1 = (
                h0_grid, h0_grid, 0.0, 1.0, 1.0, 127, 127
            )
        elif h_lod < 1.0:
            h_lod0, h_lod1, h_frac, h_scale0, h_scale1, h_mask0, h_mask1 = (
                h0_grid, h1_grid, h_lod * 0.35, 1.0, 0.5, 127, 63
            )
        else:
            f = 1.0 if h_lod >= 2.0 else (h_lod - 1.0)
            h_lod0, h_lod1, h_frac, h_scale0, h_scale1, h_mask0, h_mask1 = (
                h1_grid, h2_grid, f * 0.40, 0.5, 0.25, 63, 31
            )

        # Pre-interpolate Z rows once per depth slice (major pure-Python speedup)
        zh0 = map_z * h_scale0
        zh0_i = int(zh0)
        fzh0 = zh0 - zh0_i
        hr0_a = h_lod0[zh0_i & h_mask0]
        hr0_b = h_lod0[(zh0_i + 1) & h_mask0]
        inv_fzh0 = 1.0 - fzh0
        hrow0 = [hr0_a[i] * inv_fzh0 + hr0_b[i] * fzh0 for i in range(h_mask0 + 1)]

        if h_frac > 0.0:
            zh1 = map_z * h_scale1
            zh1_i = int(zh1)
            fzh1 = zh1 - zh1_i
            hr1_a = h_lod1[zh1_i & h_mask1]
            hr1_b = h_lod1[(zh1_i + 1) & h_mask1]
            inv_fzh1 = 1.0 - fzh1
            hrow1 = [hr1_a[i] * inv_fzh1 + hr1_b[i] * fzh1 for i in range(h_mask1 + 1)]
        else:
            hrow1 = hrow0

        zc0 = map_z * c_scale0
        zc0_i = int(zc0)
        fzc0 = zc0 - zc0_i
        inv_fzc0 = 1.0 - fzc0
        cr0_a = c_lod0[zc0_i & c_mask0]
        cr0_b = c_lod0[(zc0_i + 1) & c_mask0]

        if c_frac > 0.0:
            zc1 = map_z * c_scale1
            zc1_i = int(zc1)
            fzc1 = zc1 - zc1_i
            inv_fzc1 = 1.0 - fzc1
            cr1_a = c_lod1[zc1_i & c_mask1]
            cr1_b = c_lod1[(zc1_i + 1) & c_mask1]
            inv_c_frac = 1.0 - c_frac
        else:
            cr1_a = cr0_a
            cr1_b = cr0_b
            fzc1 = 0.0
            inv_fzc1 = 1.0
            inv_c_frac = 1.0

        inv_h_frac = 1.0 - h_frac
        cone_inv = 1.0 / (3.4 + (1.0 - depth / 102.0) * 11.0)
        depth_wave = depth * 0.22 - tau_phase
        lava_wave_z = math.sin(map_z * 0.18 - tau_phase)

        for sx in range(_SUB_W):
            cur_hf = hidden_f[sx]
            if cur_hf <= 0.0:
                continue
            map_x = camera_x + x_offsets[sx] * depth
            xh0 = map_x * h_scale0
            xh0_i = int(xh0)
            fxh0 = xh0 - xh0_i
            ix0 = xh0_i & h_mask0
            ix1 = (xh0_i + 1) & h_mask0
            height = hrow0[ix0] + (hrow0[ix1] - hrow0[ix0]) * fxh0

            if h_frac > 0.0:
                xh1 = map_x * h_scale1
                xh1_i = int(xh1)
                fxh1 = xh1 - xh1_i
                jx0 = xh1_i & h_mask1
                jx1 = (xh1_i + 1) & h_mask1
                height = height * inv_h_frac + (hrow1[jx0] + (hrow1[jx1] - hrow1[jx0]) * fxh1) * h_frac

            top_f = horizon + (camera_height - height) * inv_depth_scale
            if top_f < 0.0:
                top_f = 0.0
            elif top_f > 64.0:
                top_f = 64.0
            if top_f < cur_hf:
                xc0 = map_x * c_scale0
                xc0_i = int(xc0)
                fxc0 = xc0 - xc0_i
                inv_fxc0 = 1.0 - fxc0
                cx0 = xc0_i & c_mask0
                cx1 = (xc0_i + 1) & c_mask0
                c00 = cr0_a[cx0]
                c01 = cr0_a[cx1]
                c10 = cr0_b[cx0]
                c11 = cr0_b[cx1]
                w00 = inv_fxc0 * inv_fzc0
                w01 = fxc0 * inv_fzc0
                w10 = inv_fxc0 * fzc0
                w11 = fxc0 * fzc0
                r = c00[0] * w00 + c01[0] * w01 + c10[0] * w10 + c11[0] * w11
                g = c00[1] * w00 + c01[1] * w01 + c10[1] * w10 + c11[1] * w11
                b = c00[2] * w00 + c01[2] * w01 + c10[2] * w10 + c11[2] * w11

                if c_frac > 0.0:
                    xc1 = map_x * c_scale1
                    xc1_i = int(xc1)
                    fxc1 = xc1 - xc1_i
                    inv_fxc1 = 1.0 - fxc1
                    dx0 = xc1_i & c_mask1
                    dx1 = (xc1_i + 1) & c_mask1
                    d00 = cr1_a[dx0]
                    d01 = cr1_a[dx1]
                    d10 = cr1_b[dx0]
                    d11 = cr1_b[dx1]
                    v00 = inv_fxc1 * inv_fzc1
                    v01 = fxc1 * inv_fzc1
                    v10 = inv_fxc1 * fzc1
                    v11 = fxc1 * fzc1
                    r1 = d00[0] * v00 + d01[0] * v01 + d10[0] * v10 + d11[0] * v11
                    g1 = d00[1] * v00 + d01[1] * v01 + d10[1] * v10 + d11[1] * v11
                    b1 = d00[2] * v00 + d01[2] * v01 + d10[2] * v10 + d11[2] * v11
                    r = r * inv_c_frac + r1 * c_frac
                    g = g * inv_c_frac + g1 * c_frac
                    b = b * inv_c_frac + b1 * c_frac

                # Smooth water reflection shimmer or pulsing molten lava flow
                if height < 2.45:
                    water_mask = (2.45 - height) * 2.2222222222222223
                    if water_mask > 1.0:
                        water_mask = 1.0
                    if is_lava:
                        pulse = 0.5 + 0.5 * lava_wave_z * math.cos(map_x * 0.22)
                        lava_mix = pulse * 0.24 * water_mask
                        r += (lava_r - r) * lava_mix
                        g += (lava_g - g) * lava_mix
                        b += (lava_b - b) * lava_mix
                    elif shimmer_str > 0.0:
                        screen_x = (sx + 0.5) * 0.5
                        cone_t = 1.0 - abs(screen_x - sun_x) * cone_inv
                        if cone_t > 0.0:
                            wave = 0.65 + 0.35 * math.sin(depth_wave + screen_x * 0.20)
                            sh = cone_t * cone_t * wave * shimmer_str * water_mask
                            r += (sh_r - r) * sh
                            g += (sh_g - g) * sh
                            b += (sh_b - b) * sh

                pr = r * one_minus_haze + haze_r
                pg = g * one_minus_haze + haze_g
                pb = b * one_minus_haze + haze_b

                col = col_buf[sx]
                y_top = int(top_f)
                fr_y = fr_y_arr[sx]
                if y_top == fr_y:
                    w = cur_hf - top_f
                    nr = fr_r_arr[sx] + pr * w
                    ng = fr_g_arr[sx] + pg * w
                    nb = fr_b_arr[sx] + pb * w
                    if top_f == y_top:
                        col[y_top] = (round(nr), round(ng), round(nb))
                        fr_r_arr[sx] = 0.0
                        fr_g_arr[sx] = 0.0
                        fr_b_arr[sx] = 0.0
                    else:
                        fr_r_arr[sx] = nr
                        fr_g_arr[sx] = ng
                        fr_b_arr[sx] = nb
                    hidden_f[sx] = top_f
                else:
                    w_rem = cur_hf - fr_y
                    if w_rem > 0.0:
                        col[fr_y] = (
                            round(fr_r_arr[sx] + pr * w_rem),
                            round(fr_g_arr[sx] + pg * w_rem),
                            round(fr_b_arr[sx] + pb * w_rem),
                        )
                    pixel = (round(pr), round(pg), round(pb))
                    if top_f == y_top:
                        for y in range(y_top, fr_y):
                            col[y] = pixel
                        fr_y_arr[sx] = y_top
                        fr_r_arr[sx] = 0.0
                        fr_g_arr[sx] = 0.0
                        fr_b_arr[sx] = 0.0
                    else:
                        for y in range(y_top + 1, fr_y):
                            col[y] = pixel
                        w_top = (y_top + 1) - top_f
                        fr_y_arr[sx] = y_top
                        fr_r_arr[sx] = pr * w_top
                        fr_g_arr[sx] = pg * w_top
                        fr_b_arr[sx] = pb * w_top
                    hidden_f[sx] = top_f

    # Composite remaining fractional silhouette edge against sky
    for sx in range(_SUB_W):
        fr_y = fr_y_arr[sx]
        w_sky = hidden_f[sx] - fr_y
        if w_sky > 0.0:
            col = col_buf[sx]
            sp = col[fr_y]
            col[fr_y] = (
                round(fr_r_arr[sx] + sp[0] * w_sky),
                round(fr_g_arr[sx] + sp[1] * w_sky),
                round(fr_b_arr[sx] + sp[2] * w_sky),
            )

    # Box-average pairs of sub-columns down to 64x64
    out_pixels: list[tuple[int, int, int]] = [(0, 0, 0)] * (64 * 64)
    for x in range(64):
        c_left = col_buf[x * 2]
        c_right = col_buf[x * 2 + 1]
        for y in range(64):
            a = c_left[y]
            b = c_right[y]
            out_pixels[y * 64 + x] = (
                (a[0] + b[0] + 1) >> 1,
                (a[1] + b[1] + 1) >> 1,
                (a[2] + b[2] + 1) >> 1,
            )
    image = Image.new("RGB", (64, 64))
    image.putdata(out_pixels)
    return image


def _frame(
    heights: list,
    colors: list,
    palette: dict,
    phase: float,
    *,
    scene: _SceneParams | None = None,
) -> Image.Image:
    """Draw depth slices from the camera to the horizon, hiding occluded pixels."""
    if scene is None:
        palette_name = _palette_name_for(palette)
        scene = _build_scene(731, palette_name, "fjord", default_corridor=True)
    h_mips, c_mips = _prepare_mips(heights, colors)
    sky = _SkyRenderer(palette, scene)
    camera_profile = _camera_altitude_profile(heights, scene)
    return _render_frame(
        h_mips, c_mips, sky, scene, _camera_height_at(camera_profile, phase), phase
    )


def render(
    settings: Settings, config: dict[str, str], output: Path, output_large: Path
) -> None:
    seed = int(config["seed"]) if config.get("seed") else random.randint(1, 999999)
    palette_name = _resolve_palette_name(config.get("palette"), seed)
    terrain_name = _resolve_terrain_name(config.get("terrain"), seed, palette_name)
    palette = PALETTES[palette_name]
    scene = _build_scene(seed, palette_name, terrain_name)

    heights, colors = _terrain(seed, palette, terrain=terrain_name, scene=scene)
    h_mips, c_mips = _prepare_mips(heights, colors)
    sky = _SkyRenderer(palette, scene)
    camera_profile = _camera_altitude_profile(heights, scene)

    frames = [
        _render_frame(
            h_mips,
            c_mips,
            sky,
            scene,
            _camera_height_at(camera_profile, index / FRAME_COUNT),
            index / FRAME_COUNT,
        )
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
        lossless=False,
        quality=90,
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
        lossless=False,
        quality=90,
    )
