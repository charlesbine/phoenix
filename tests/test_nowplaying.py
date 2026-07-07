"""Now-playing card — position extrapolation + frame rendering (no HA/panel)."""

import time

from phoenix.nowplaying.render import NowPlayingRenderer
from phoenix.nowplaying.source import Track


def test_progress_extrapolates_only_while_playing():
    playing = Track(title="x", duration=100, playing=True, _position=10)
    assert 0.09 <= playing.progress() <= 0.25  # ~10% right after capture

    paused = Track(title="x", duration=100, playing=False, _position=50)
    p1 = paused.position_now()
    time.sleep(0.02)
    assert paused.position_now() == p1  # frozen when not playing


def test_position_capped_at_duration():
    t = Track(title="x", duration=5, playing=True, _position=4.99)
    time.sleep(0.05)
    assert t.position_now() <= 5.0


def test_render_frames_are_full_size():
    r = NowPlayingRenderer()
    t = Track(title="A Long Song Title That Definitely Scrolls", artist="Artist",
              duration=200, playing=True, _position=100)
    assert len(r.render(t, 0.1)) == 64 * 64 * 3
    assert len(r.render_idle()) == 64 * 64 * 3


def test_scroll_advances_then_resets_on_track_change():
    r = NowPlayingRenderer()
    long1 = Track(title="A very very long title that scrolls across", artist="B",
                  duration=100, playing=True)
    r.render(long1, 0.5)
    r.render(long1, 0.5)
    assert r._scroll > 0  # scrolled while the long title stayed put

    long2 = Track(title="A different very long title also scrolling", artist="C",
                  duration=100, playing=True)
    r.render(long2, 0.0)
    assert r._scroll == 0.0  # reset when the track changes
