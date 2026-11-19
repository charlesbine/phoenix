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
    for output, size in ((native, 64), (large, 128)):
        with Image.open(output) as image:
            assert image.size == (size, size)
            assert image.info["loop"] == 0
            assert image.n_frames == landscape.FRAME_COUNT
            duration = 0
            for frame in ImageSequence.Iterator(image):
                frame.load()
                duration += frame.info["duration"]
            assert duration == 12_000
    assert default_preset_for("procedural_landscape") == "ambient"


def test_bad_palette_is_actionable(tmp_path):
    with pytest.raises(ValueError, match="Unknown landscape palette"):
        landscape.render(
            Settings(_env_file=None),
            {"palette": "missing"},
            tmp_path / "native.webp",
            tmp_path / "large.webp",
        )
