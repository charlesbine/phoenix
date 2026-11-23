"""Loop and frame timing checks for the shared planet generator."""

import io

import pytest
from PIL import Image, ImageChops, ImageSequence, ImageStat

from phoenix.apps.procedural_planet import render
from phoenix.procedural.pixel_planet import (
    PLANET_TYPES,
    _planet_uv,
    generate_planet_gif,
)
from phoenix.settings import Settings


def _frame_difference(first: Image.Image, second: Image.Image) -> float:
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean)


def _assert_loop(source, duration_ms: int) -> None:
    with Image.open(source) as animation:
        assert animation.info["loop"] == 0
        frames = []
        total_ms = 0
        for frame in ImageSequence.Iterator(animation):
            frames.append(frame.convert("RGB"))
            total_ms += frame.info["duration"]

    assert total_ms == duration_ms
    steps = [
        _frame_difference(first, second) for first, second in zip(frames, frames[1:])
    ]
    wrap = _frame_difference(frames[-1], frames[0])
    assert 0 < wrap <= max(steps)


@pytest.mark.parametrize("planet_type", PLANET_TYPES)
def test_generated_gif_wraps_like_an_ordinary_frame_step(planet_type):
    gif = generate_planet_gif(
        planet_type, seed=2319, size=20, n_frames=25, frame_delay_ms=400
    )
    _assert_loop(io.BytesIO(gif), duration_ms=10_000)


def test_procedural_planet_webps_keep_the_loop_and_timing(tmp_path):
    native = tmp_path / "planet.webp"
    large = tmp_path / "planet_large.webp"
    render(
        Settings(magnification=2),
        {
            "planet_type": "lava",
            "seed": "2319",
            "time_speed": "0.2",
            "n_frames": "25",
            "frame_delay": "400",
        },
        native,
        large,
    )
    for output in (native, large):
        _assert_loop(output, duration_ms=6_250)


def test_procedural_planet_softens_frame_changes_across_loop_boundary(tmp_path, monkeypatch):
    source = [Image.new("RGB", (64, 64)) for _ in range(4)]
    for frame, color in zip(source, [(0, 0, 0), (200, 0, 0), (0, 200, 0), (0, 0, 200)]):
        frame.putpixel((32, 32), color)
    gif = io.BytesIO()
    source[0].save(
        gif, "GIF", save_all=True, append_images=source[1:], duration=[60, 70, 70, 70], loop=0,
    )
    monkeypatch.setattr("phoenix.apps.procedural_planet.generate_planet_gif", lambda **kwargs: gif.getvalue())

    native, large = tmp_path / "planet.webp", tmp_path / "planet.large.webp"
    render(Settings(_env_file=None, magnification=2), {}, native, large)

    for path, center in [(native, 32), (large, 64)]:
        with Image.open(path) as animation:
            frames = [frame.convert("RGB") for frame in ImageSequence.Iterator(animation)]
        assert [frame.getpixel((center, center)) for frame in frames] == [
            (50, 0, 50), (100, 50, 0), (50, 100, 50), (0, 50, 100),
        ]
        assert all(frame.getpixel((0, 0)) == (0, 0, 0) for frame in frames)


def test_zero_speed_renders_a_still_planet():
    gif = generate_planet_gif("lava", seed=2319, size=16, n_frames=4, time_speed=0)
    with Image.open(io.BytesIO(gif)) as image:
        assert image.n_frames == 1


@pytest.mark.parametrize(("speed", "screen_direction"), [(0.1, -1), (-0.1, 1)])
def test_longitude_keeps_the_same_direction_through_the_wrap(
    monkeypatch, speed, screen_direction
):
    def render_marker(cfg, phase):
        frame = Image.new("RGBA", (cfg.size, cfg.size))
        for x in range(cfg.size):
            longitude, _ = _planet_uv((x + 0.5) / cfg.size, 0.5, phase)
            if 0.47 <= longitude <= 0.53:
                frame.putpixel((x, cfg.size // 2), (255, 255, 255, 255))
        return frame

    monkeypatch.setitem(PLANET_TYPES, "marker", render_marker)
    gif = generate_planet_gif("marker", size=32, n_frames=16, time_speed=speed)
    with Image.open(io.BytesIO(gif)) as animation:
        bounds = [
            frame.convert("RGB").getbbox()
            for frame in ImageSequence.Iterator(animation)
        ]

    last, first, second = (bounds[index][0] for index in (-1, 0, 1))
    assert screen_direction * (first - last) > 0
    assert screen_direction * (second - first) > 0


@pytest.mark.parametrize(
    ("speed", "frame_delay", "expected_ms"),
    [
        (0.052, 400, 12_500),
        (-0.052, 400, 12_500),
        (0.9, 400, 6_250),
        (0.08, 900, 15_000),
        (0.16, 4, 5_000),
    ],
)
def test_speed_limits_keep_frame_steps_and_holds_small(
    monkeypatch, speed, frame_delay, expected_ms
):
    phases = []

    def render_distinct_frame(cfg, phase):
        phases.append(phase)
        sample_index = len(phases)
        color = (sample_index % 256, sample_index // 256, 0, 255)
        return Image.new("RGBA", (cfg.size, cfg.size), color)

    monkeypatch.setitem(PLANET_TYPES, "cadence-test", render_distinct_frame)
    data = generate_planet_gif(
        "cadence-test",
        size=4,
        n_frames=25,
        frame_delay_ms=frame_delay,
        time_speed=speed,
    )
    with Image.open(io.BytesIO(data)) as animation:
        assert animation.n_frames >= 100
        durations = [
            frame.info["duration"] for frame in ImageSequence.Iterator(animation)
        ]

    assert sum(durations) == expected_ms
    assert min(durations) >= 40
    assert max(durations) <= 70
    assert max(durations) - min(durations) <= 10

    elapsed_ms = 0
    direction = -1 if speed < 0 else 1
    for phase, hold_ms in zip(phases, durations, strict=True):
        assert phase == pytest.approx(direction * elapsed_ms / expected_ms)
        elapsed_ms += hold_ms
