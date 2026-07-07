"""The shared FramePlayer — decode a webp and stream frames to a FrameSink.

This is the loop that used to be copy-pasted into every backend; here we prove
it against a recording fake sink (no hardware): stills send once, lossy sinks
re-send, animations decode every frame, and a dead transport bails.
"""

import pytest
from PIL import Image

from phoenix.display import sink as sink_mod
from phoenix.display.sink import FRAME_BYTES, FramePlayer


class RecSink:
    """Records every frame + brightness it's handed."""

    still_refresh = 0.0

    def __init__(self, fail: bool = False):
        self.frames: list[bytes] = []
        self.brightness: list[int] = []
        self._fail = fail

    def send_frame(self, rgb: bytes) -> bool:
        self.frames.append(rgb)
        return not self._fail

    def set_brightness(self, level: int) -> None:
        self.brightness.append(level)

    def clear(self) -> None:
        pass

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # Run the timing loops instantly.
    monkeypatch.setattr(sink_mod.time, "sleep", lambda _s: None)


def _still(path):
    Image.new("RGB", (64, 64), (10, 20, 30)).save(path, "WEBP")
    return path


def _animation(path, frames=3):
    imgs = [Image.new("RGB", (64, 64), (i * 40, 0, 0)) for i in range(frames)]
    imgs[0].save(path, "WEBP", save_all=True, append_images=imgs[1:], duration=50, loop=0)
    return path


def test_still_sends_one_full_frame_at_brightness(tmp_path):
    sink = RecSink()
    FramePlayer(sink).play(_still(tmp_path / "s.webp"), 0, lambda: 128, lambda: False)
    assert len(sink.frames) == 1
    assert len(sink.frames[0]) == FRAME_BYTES
    assert sink.brightness[0] == 128


def test_reliable_sink_does_not_resend_stills(tmp_path):
    sink = RecSink()  # still_refresh = 0
    FramePlayer(sink).play(_still(tmp_path / "s.webp"), 2, lambda: 200, lambda: False)
    assert len(sink.frames) == 1  # held once, never re-sent


def test_lossy_sink_resends_stills(tmp_path):
    sink = RecSink()
    sink.still_refresh = 0.5  # emulate WLED
    FramePlayer(sink).play(_still(tmp_path / "s.webp"), 2, lambda: 200, lambda: False)
    assert len(sink.frames) > 1  # re-sent to self-heal dropped packets


def test_still_bails_when_transport_down(tmp_path):
    sink = RecSink(fail=True)
    FramePlayer(sink).play(_still(tmp_path / "s.webp"), 5, lambda: 128, lambda: False)
    assert len(sink.frames) == 1  # one attempt, then back off — no spin


def test_interrupt_stops_a_still_early(tmp_path):
    sink = RecSink()
    calls = {"n": 0}

    def interrupt() -> bool:
        calls["n"] += 1
        return True  # notification pending → break out immediately

    FramePlayer(sink).play(_still(tmp_path / "s.webp"), 60, lambda: 128, interrupt)
    assert calls["n"] == 1  # checked once, returned — didn't sleep out the 60s


def test_animation_decodes_and_streams_every_frame(tmp_path):
    frames, durations = FramePlayer._extract(Image.open(_animation(tmp_path / "a.webp", frames=3)))
    assert len(frames) == 3 and len(durations) == 3
    assert all(len(f) == FRAME_BYTES for f in frames)

    sink = RecSink()
    seq = iter([False, False, False])  # allow 3 frames, then interrupt
    FramePlayer(sink).play(
        _animation(tmp_path / "a.webp", frames=3), 60, lambda: 100, lambda: next(seq, True)
    )
    assert len(sink.frames) == 3
