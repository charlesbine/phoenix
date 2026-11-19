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
        landscape._resolve_palette_name("auto", seed) for seed in range(1, 60)
    }
    seen_terrains = {
        landscape._resolve_terrain_name("auto", seed, landscape._resolve_palette_name("auto", seed))
        for seed in range(1, 60)
    }
    assert len(seen_palettes) >= 8
    assert set(seen_terrains) == set(landscape.TERRAINS)
    # Missing/empty values match explicit "auto"
    assert landscape._resolve_palette_name(None, 731) == landscape._resolve_palette_name("auto", 731)
    assert landscape._resolve_palette_name("", 731) == landscape._resolve_palette_name("auto", 731)
    assert landscape._resolve_terrain_name(None, 731, "dusk") == landscape._resolve_terrain_name(
        "auto", 731, "dusk"
    )


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
