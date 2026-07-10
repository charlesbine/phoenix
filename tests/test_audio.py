"""Audio visualizer DSP — analyzer + bars, verified with synthetic tones.

No hardware: SyntheticSource stands in for the capture device, so the FFT
banding and the frame rendering are fully deterministic.
"""

import shutil
import wave

import numpy as np
import pytest

from phoenix.audio.analyzer import SpectrumAnalyzer
from phoenix.audio.source import FileAudioSource, SyntheticSource
from phoenix.audio.visualizer import (
    SPECTROGRAM_PALETTE_OPTIONS,
    Spectrogram,
    SpectrumBars,
    VUMeter,
    make_visualizer,
)


def test_synthetic_source_shape():
    src = SyntheticSource(440.0, blocksize=512, blocks=3)
    got = list(src.blocks())
    assert len(got) == 3
    assert all(b.shape == (512,) and b.dtype == np.float32 for b in got)


def test_analyzer_locates_a_tone():
    sr, n, bands = 44100, 2048, 24
    analyzer = SpectrumAnalyzer(samplerate=sr, fft_size=n, bands=bands)
    levels = np.zeros(bands, dtype=np.float32)
    for blk in SyntheticSource(1000.0, samplerate=sr, blocksize=n, blocks=12, amplitude=0.6).blocks():
        levels, _peaks = analyzer.process(blk)

    edges = np.logspace(np.log10(40), np.log10(16000), bands + 1)
    expected = int(np.searchsorted(edges, 1000.0) - 1)
    assert abs(int(np.argmax(levels)) - expected) <= 1  # tone lands in its band
    assert levels.max() > 0.3  # and it's clearly present


def test_analyzer_silence_is_quiet():
    analyzer = SpectrumAnalyzer(fft_size=1024)
    levels, peaks = analyzer.process(np.zeros(1024, dtype=np.float32))
    assert levels.max() < 0.05 and peaks.max() < 0.05


def test_analyzer_noise_gate_suppresses_quiet_residual_energy():
    quiet = next(SyntheticSource(120.0, blocksize=1024, blocks=1, amplitude=0.005).blocks())
    open_analyzer = SpectrumAnalyzer(fft_size=1024, floor_db=-70, noise_gate=0.0)
    gated_analyzer = SpectrumAnalyzer(fft_size=1024, floor_db=-70, noise_gate=0.12)

    open_levels, _ = open_analyzer.process(quiet)
    gated_levels, _ = gated_analyzer.process(quiet)

    assert open_levels.max() > 0.0
    assert gated_levels.max() < open_levels.max()


def test_analyzer_onset_boost_emphasizes_positive_spectral_changes():
    quiet = next(SyntheticSource(80.0, blocksize=1024, blocks=1, amplitude=0.02).blocks())
    loud = next(SyntheticSource([80.0, 1200.0], blocksize=1024, blocks=1, amplitude=0.18).blocks())
    plain = SpectrumAnalyzer(fft_size=1024, floor_db=-70, noise_gate=0.0, onset_boost=0.0)
    boosted = SpectrumAnalyzer(fft_size=1024, floor_db=-70, noise_gate=0.0, onset_boost=1.4)

    plain.process(quiet)
    boosted.process(quiet)
    plain_levels, _ = plain.process(loud)
    boosted_levels, _ = boosted.process(loud)

    assert boosted_levels.max() > plain_levels.max()


def test_bars_render_black_when_silent():
    viz = SpectrumBars(bands=16, size=64)
    z = np.zeros(16, dtype=np.float32)
    out = viz.render(z, z)
    assert len(out) == 64 * 64 * 3
    assert set(out) == {0}  # nothing lit


def test_bars_light_only_the_active_band():
    bands, size = 16, 64
    viz = SpectrumBars(bands=bands, size=size)
    levels = np.zeros(bands, dtype=np.float32)
    levels[0] = 1.0  # only the lowest band, full height
    frame = np.frombuffer(viz.render(levels, levels), dtype=np.uint8).reshape(size, size, 3)

    assert frame[:, 0:3].any()        # leftmost band's columns are lit
    assert not frame[:, -3:].any()    # rightmost columns stay dark
    assert frame[0, 0:3].any()        # a full-height bar reaches the top row


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required to decode files")
def test_file_source_decodes_and_locates_tone(tmp_path):
    sr, n, bands = 44100, 2048, 24
    t = np.arange(sr) / sr  # 1 second
    pcm = (0.6 * np.sin(2 * np.pi * 1000.0 * t) * 32767).astype("<i2")
    wav = tmp_path / "tone.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())

    blocks = list(FileAudioSource(wav, samplerate=sr, blocksize=n).blocks())
    assert len(blocks) > 10 and all(b.shape == (n,) for b in blocks)

    analyzer = SpectrumAnalyzer(samplerate=sr, fft_size=n, bands=bands)
    levels = np.zeros(bands, dtype=np.float32)
    for b in blocks[:12]:
        levels, _ = analyzer.process(b)
    edges = np.logspace(np.log10(40), np.log10(16000), bands + 1)
    expected = int(np.searchsorted(edges, 1000.0) - 1)
    assert abs(int(np.argmax(levels)) - expected) <= 1


def test_bars_peak_cap_sits_above_a_short_bar():
    viz = SpectrumBars(bands=8, size=64)
    levels = np.zeros(8, dtype=np.float32)
    peaks = np.zeros(8, dtype=np.float32)
    levels[3] = 0.25
    peaks[3] = 0.75  # peak held well above the current level
    frame = np.frombuffer(viz.render(levels, peaks), dtype=np.uint8).reshape(64, 64, 3)

    lit_rows = np.where(frame.any(axis=(1, 2)))[0]
    # highest lit row (smallest y) is the cap, near y = 64*(1-0.75) = 16
    assert lit_rows.min() <= 20


def test_bars_can_render_exact_two_pixel_solid_columns():
    viz = SpectrumBars(bands=32, size=64, bar_width=2, gap=0)
    levels = np.linspace(0.05, 1.0, 32, dtype=np.float32)
    frame = np.frombuffer(viz.render(levels, levels), dtype=np.uint8).reshape(64, 64, 3)

    for x in range(0, 64, 2):
        assert np.array_equal(frame[:, x], frame[:, x + 1])


def test_vu_fills_more_when_louder():
    viz = VUMeter(bands=24, size=64)
    z = np.zeros(24, dtype=np.float32)
    o = np.ones(24, dtype=np.float32)
    quiet = np.frombuffer(viz.render(z, z), dtype=np.uint8)
    loud = np.frombuffer(viz.render(o, o), dtype=np.uint8)
    assert len(loud) == 64 * 64 * 3
    assert (loud > 0).sum() > (quiet > 0).sum()  # louder → more segments lit


def test_spectrogram_scrolls_left():
    viz = Spectrogram(bands=24, size=64)
    bright = np.ones(24, dtype=np.float32)
    silent = np.zeros(24, dtype=np.float32)
    viz.render(bright, bright)  # newest bright column at x=63
    frame = np.frombuffer(viz.render(silent, silent), dtype=np.uint8).reshape(64, 64, 3)
    assert frame[:, 62].any()       # the bright column scrolled one step left
    assert not frame[:, 63].any()   # newest (silent) column is dark


def test_spectrogram_can_render_exact_two_pixel_frequency_rows():
    viz = Spectrogram(bands=32, size=64, bar_width=2)
    levels = np.linspace(0.0, 1.0, 32, dtype=np.float32)

    frame = np.frombuffer(viz.render(levels, levels), dtype=np.uint8).reshape(64, 64, 3)
    newest = frame[:, 63]

    for y in range(0, 64, 2):
        assert np.array_equal(newest[y], newest[y + 1])


@pytest.mark.parametrize("palette", [value for value, _display in SPECTROGRAM_PALETTE_OPTIONS])
def test_spectrogram_palettes_color_by_intensity_not_frequency(palette):
    viz = Spectrogram(bands=32, size=64, bar_width=2, palette=palette)
    levels = np.zeros(32, dtype=np.float32)
    levels[0] = 0.7
    levels[-1] = 0.7

    frame = np.frombuffer(viz.render(levels, levels), dtype=np.uint8).reshape(64, 64, 3)
    newest = frame[:, 63]

    assert newest[0].any()
    assert newest[-1].any()
    assert np.array_equal(newest[0], newest[-1])


def test_make_visualizer_selects_mode():
    assert isinstance(make_visualizer("vu", 24), VUMeter)
    assert isinstance(make_visualizer("spectrogram", 24), Spectrogram)
    assert isinstance(make_visualizer("spectrogram", 32, bar_width=2), Spectrogram)
    assert isinstance(make_visualizer("bars", 32, bar_width=2, gap=0), SpectrumBars)
    assert isinstance(make_visualizer("bars", 24), SpectrumBars)
    with pytest.raises(ValueError):
        make_visualizer("nope", 24)
