"""The flyover uses a closed flight path and preserves exported animation timing."""

import pytest
from PIL import Image, ImageSequence

from phoenix.apps import procedural_landscape as landscape
from phoenix.models import default_preset_for
from phoenix.settings import Settings


@pytest.mark.parametrize("palette", landscape.PALETTES)
def test_seeded_terrain_and_flight_path_repeat(palette):
    colors = landscape.PALETTES[palette]
    heights, texture = landscape._terrain(731, colors)
    assert (heights, texture) == landscape._terrain(731, colors)
    for phase in (0.0, 0.25, 0.75):
        first = landscape._frame(heights, texture, colors, phase)
        repeated = landscape._frame(heights, texture, colors, phase + 1)
        assert first.size == (64, 64)
        assert first.tobytes() == repeated.tobytes()
    assert (
        landscape._frame(heights, texture, colors, 0).tobytes()
        != landscape._frame(heights, texture, colors, 0.25).tobytes()
    )


@pytest.mark.parametrize("terrain", landscape.TERRAINS)
def test_terrain_archetypes_produce_valid_wrapping_worlds(terrain):
    palette = landscape.PALETTES["dusk"]
    scene = landscape._build_scene(512, "dusk", terrain)
    heights, texture = landscape._terrain(512, palette, terrain=terrain, scene=scene)
    assert len(heights) == landscape.MAP_SIZE
    assert len(texture) == landscape.MAP_SIZE
    assert (heights, texture) == landscape._terrain(512, palette, terrain=terrain, scene=scene)
    first = landscape._frame(heights, texture, palette, 0.1, scene=scene)
    wrapped = landscape._frame(heights, texture, palette, 1.1, scene=scene)
    assert first.size == (64, 64)
    assert first.tobytes() == wrapped.tobytes()


def test_auto_selection_varies_worlds_across_seeds():
    seen_palettes = {
        landscape._resolve_palette_name("auto", seed) for seed in range(1, 80)
    }
    terrains = [
        landscape._resolve_terrain_name("auto", seed, landscape._resolve_palette_name("auto", seed))
        for seed in range(1, 181)
    ]
    assert len(seen_palettes) >= 8
    assert set(terrains) == set(landscape.TERRAINS)
    # Fjord is the sole corridor archetype and should be a balanced slice (~1/6), not the majority
    fjord_ratio = terrains.count("fjord") / len(terrains)
    assert 0.05 <= fjord_ratio <= 0.30
    # Missing/empty values match explicit "auto"
    assert landscape._resolve_palette_name(None, 731) == landscape._resolve_palette_name("auto", 731)
    assert landscape._resolve_palette_name("", 731) == landscape._resolve_palette_name("auto", 731)
    assert landscape._resolve_terrain_name(None, 731, "dusk") == landscape._resolve_terrain_name(
        "auto", 731, "dusk"
    )


def test_peaks_uses_periodic_dynamic_camera_altitude_without_carved_road():
    palette = landscape.PALETTES["alpine"]
    scene = landscape._build_scene(101, "alpine", "peaks")
    heights, _ = landscape._terrain(101, palette, terrain="peaks", scene=scene)
    profile = landscape._camera_altitude_profile(heights, scene)
    # Dynamic periodic Fourier profile (not a flat constant)
    assert len(profile[1]) >= 1
    samples = [landscape._camera_height_at(profile, i / 64.0) for i in range(64)]
    assert max(samples) - min(samples) > 0.2
    for phase in (0.0, 0.17, 0.5, 0.83):
        assert landscape._camera_height_at(profile, phase) == pytest.approx(
            landscape._camera_height_at(profile, phase + 1.0)
        )
    # Camera clears all terrain immediately beneath the flight path
    for z in range(landscape.MAP_SIZE):
        cx = (
            int(round(landscape._channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase)))
            & 127
        )
        cam_h = landscape._camera_height_at(profile, z / landscape.MAP_SIZE)
        assert cam_h >= heights[z][cx] + 4.0
    # No carved water corridor down the flight path center
    center_heights = [
        heights[z][
            int(round(landscape._channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase)))
            & 127
        ]
        for z in range(landscape.MAP_SIZE)
    ]
    assert sum(1 for h in center_heights if h > 6.0) > landscape.MAP_SIZE * 0.7


def test_dunes_and_canyon_are_dry_and_road_free():
    # Dunes: zero water channel, continuous sweeping elevation across the whole map
    dunes_scene = landscape._build_scene(202, "desert", "dunes")
    assert dunes_scene.has_water_channel is False
    dunes_h, _ = landscape._terrain(202, landscape.PALETTES["desert"], terrain="dunes", scene=dunes_scene)
    dunes_flat = [h for row in dunes_h for h in row]
    assert min(dunes_flat) > landscape._WATER_LEVEL + 1.5
    assert max(dunes_flat) - min(dunes_flat) > 8.0

    # Canyon: dry basin floor with tall scattered mesas (no water canal)
    canyon_scene = landscape._build_scene(404, "mars", "canyon")
    assert canyon_scene.has_water_channel is False
    canyon_h, _ = landscape._terrain(404, landscape.PALETTES["mars"], terrain="canyon", scene=canyon_scene)
    canyon_flat = [h for row in canyon_h for h in row]
    assert min(canyon_flat) > landscape._WATER_LEVEL + 1.5
    assert max(canyon_flat) > 18.0


def test_coast_archetype_is_one_sided_and_varies_side_by_seed():
    assert "coast" in landscape.TERRAINS
    terrain_field = next(f for f in landscape.SETTINGS_SCHEMA if f["id"] == "terrain")
    assert any(opt["value"] == "coast" for opt in terrain_field["options"])

    sides = {landscape._build_scene(seed, "sunset", "coast").coast_side for seed in range(1, 30)}
    assert sides == {-1, 1}

    scene = landscape._build_scene(303, "sunset", "coast")
    heights, _ = landscape._terrain(303, landscape.PALETTES["sunset"], terrain="coast", scene=scene)
    side = scene.coast_side
    land_side_vals = []
    sea_side_vals = []
    for z in range(landscape.MAP_SIZE):
        ch = landscape._channel_center(z, scene.sway_a, scene.sway_b, scene.sway_phase)
        land_x = int(round(ch + side * 24.0)) & 127
        sea_x = int(round(ch - side * 24.0)) & 127
        land_side_vals.append(heights[z][land_x])
        sea_side_vals.append(heights[z][sea_x])
    # Towering cliffs on the land side, predominantly open ocean on the sea side
    assert sum(land_side_vals) / len(land_side_vals) > 14.0
    assert sum(1 for h in sea_side_vals if h <= landscape._WATER_LEVEL + 0.1) > landscape.MAP_SIZE * 0.8


def test_landscape_render_entry_point_keeps_animation(tmp_path, monkeypatch):
    native = tmp_path / "native.webp"
    large = tmp_path / "large.webp"
    from phoenix import render
    from phoenix.models import AppConfig

    monkeypatch.setattr(render, "output_path", lambda name: native)
    monkeypatch.setattr(render, "output_path_large", lambda name: large)
    render._render_dispatch(
        AppConfig(name="procedural_landscape", pixlet_config={"seed": "731"}),
        Settings(_env_file=None, magnification=2),
    )
    assert native.stat().st_size < 180 * 1024
    for output, size in ((native, 64), (large, 128)):
        with Image.open(output) as image:
            assert image.size == (size, size)
            assert image.info["loop"] == 0
            assert image.n_frames == landscape.FRAME_COUNT
            duration = 0
            frames_bytes = []
            for frame in ImageSequence.Iterator(image):
                frame.load()
                duration += frame.info["duration"]
                if size == 64:
                    frames_bytes.append(frame.convert("RGB").tobytes())
            assert duration == 12_000
            if size == 64:
                # Confirm smooth temporal transitions and clean wrap seam
                seam_l1 = sum(abs(a - b) for a, b in zip(frames_bytes[0], frames_bytes[-1])) / (
                    64 * 64 * 3
                )
                assert seam_l1 < 5.0
    assert default_preset_for("procedural_landscape") == "ambient"


def test_bad_palette_is_actionable(tmp_path):
    with pytest.raises(ValueError, match="Unknown landscape palette"):
        landscape.render(
            Settings(_env_file=None),
            {"palette": "missing"},
            tmp_path / "native.webp",
            tmp_path / "large.webp",
        )


def test_bad_terrain_is_actionable(tmp_path):
    with pytest.raises(ValueError, match="Unknown landscape terrain"):
        landscape.render(
            Settings(_env_file=None),
            {"palette": "dusk", "terrain": "missing"},
            tmp_path / "native.webp",
            tmp_path / "large.webp",
        )
