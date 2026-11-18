"""Visualizers — band levels → a 64x64 RGB frame (raw bytes for the FrameSink).

SpectrumBars draws the classic analyzer: one vertical bar per band, colored with
the Ember-CRT fire gradient (crimson embers at the base → gold/core at the tip),
with a bright peak-hold cap. Rendered straight into a numpy buffer so it's cheap
enough for ~45fps and deterministic for tests.
"""

from typing import Protocol

import numpy as np

from phoenix.models import SPECTROGRAM_PALETTE_OPTIONS as SPECTROGRAM_PALETTE_OPTIONS

SIZE = 64

# Ember-CRT fire ramp, base → tip.
_PALETTE = np.array(
    [
        (95, 12, 8),     # deep ember
        (179, 36, 26),   # crimson
        (255, 90, 42),   # ember
        (255, 158, 61),  # flame
        (255, 217, 138), # gold
        (255, 242, 207), # core
    ],
    dtype=np.float32,
)
_CAP = np.array((255, 242, 207), dtype=np.uint8)  # peak-hold cap = core white-gold


def _ramp(colors: np.ndarray, n: int) -> np.ndarray:
    """Interpolate a small palette to an (n, 3) uint8 ramp."""
    colors = np.asarray(colors, dtype=np.float32)
    xs = np.linspace(0.0, len(colors) - 1, n)
    base = np.arange(len(colors))
    out = np.empty((n, 3), dtype=np.uint8)
    for c in range(3):
        out[:, c] = np.interp(xs, base, colors[:, c]).astype(np.uint8)
    return out


def _fire_gradient(height: int) -> np.ndarray:
    """(height, 3) uint8 ramp; row 0 = bar base, row height-1 = tip."""
    return _ramp(_PALETTE, height)


def _spectrogram_palette(colors: list[tuple[int, int, int]]) -> np.ndarray:
    return _ramp(np.array(colors, dtype=np.float32), 256)


# Every spectrogram palette is an intensity map: black/silent at index 0,
# loudest energy at index 255. Frequency position never changes the color.
_SPECTROGRAM_PALETTES = {
    "hue": _spectrogram_palette(
        [
            (0, 0, 0),
            (9, 12, 55),
            (18, 55, 145),
            (0, 170, 210),
            (20, 205, 125),
            (255, 217, 64),
            (255, 104, 34),
            (255, 242, 207),
        ]
    ),
    "fire": _spectrogram_palette(
        [
            (0, 0, 0),
            (40, 10, 6),
            (179, 36, 26),
            (255, 90, 42),
            (255, 158, 61),
            (255, 217, 138),
            (255, 242, 207),
        ]
    ),
    "ice": _spectrogram_palette(
        [
            (0, 0, 0),
            (5, 18, 36),
            (12, 72, 120),
            (28, 150, 195),
            (112, 220, 232),
            (220, 252, 255),
        ]
    ),
    "aurora": _spectrogram_palette(
        [
            (0, 0, 0),
            (12, 28, 40),
            (23, 108, 92),
            (34, 205, 138),
            (140, 238, 86),
            (250, 255, 190),
        ]
    ),
    "mono": _spectrogram_palette(
        [
            (0, 0, 0),
            (24, 24, 24),
            (84, 84, 84),
            (160, 160, 160),
            (255, 255, 255),
        ]
    ),
}
# VU ramp: amber when quiet → red-hot when slammed.
_VU = _ramp(
    np.array([(120, 62, 18), (255, 158, 61), (255, 217, 138), (255, 90, 42), (196, 28, 14)],
             dtype=np.float32),
    64,
)


class Visualizer(Protocol):
    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes: ...


class SpectrumBars:
    def __init__(self, bands: int = 24, size: int = SIZE, gap: int = 0, bar_width: int | None = None):
        self.bands = bands
        self.size = size
        self.gap = gap
        self._grad = _fire_gradient(size)  # color per height-from-base
        if bar_width is None:
            bar_width = max(1, (size - max(0, bands - 1) * gap) // bands)
        if bar_width < 1 or gap < 0:
            raise ValueError("bar_width must be >= 1 and gap must be >= 0")
        used = bands * bar_width + max(0, bands - 1) * gap
        if used > size:
            raise ValueError(f"{bands} bars of width {bar_width} with gap {gap} do not fit in {size}px")
        start = (size - used) // 2
        self._spans = [
            (start + b * (bar_width + gap), start + b * (bar_width + gap) + bar_width)
            for b in range(bands)
        ]

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        size = self.size
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        for b, (x0, x1) in enumerate(self._spans):
            h = int(round(float(levels[b]) * size))
            if h > 0:
                h = min(h, size)
                # rows size-h .. size-1 (bottom-anchored); color by height-from-base
                frame[size - h : size, x0:x1] = self._grad[:h][::-1, None, :]

            ph = int(round(float(peaks[b]) * size))
            if ph > 0:
                y = size - min(ph, size)
                frame[y, x0:x1] = _CAP

        return frame.tobytes()


class VUMeter:
    """A fat segmented loudness meter — overall level fills left→right, amber to
    red-hot, with a peak-hold segment. Reads the mean of the band levels."""

    def __init__(self, bands: int = 24, size: int = SIZE, segments: int = 32, gain: float = 1.3):
        self.size = size
        self.segments = segments
        self.gain = gain
        self._colors = _ramp(_VU, segments)

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        size = self.size
        frame = np.zeros((size, size, 3), dtype=np.uint8)
        level = float(np.clip(levels.mean() * self.gain, 0.0, 1.0))
        pk = float(np.clip(peaks.mean() * self.gain, 0.0, 1.0))

        y0, y1 = size // 2 - 10, size // 2 + 10  # a 20px-tall bar
        lit = int(round(level * self.segments))
        seg_w = size / self.segments
        for s in range(lit):
            x0 = int(round(s * seg_w))
            x1 = max(x0 + 1, int(round((s + 1) * seg_w)) - 1)
            frame[y0:y1, x0:x1] = self._colors[s]

        ps = int(round(pk * self.segments)) - 1
        if 0 <= ps < self.segments:
            x0 = int(round(ps * seg_w))
            x1 = max(x0 + 1, int(round((ps + 1) * seg_w)) - 1)
            frame[y0:y1, x0:x1] = _CAP
        return frame.tobytes()


_CONTRAST_GAMMA = {
    "classic": 1.0,
    "high": 0.58,
    "hot": 0.42,
}


class Spectrogram:
    """Scrolling waterfall — each frame adds the current spectrum as the
    rightmost column (low freq at the bottom) and scrolls history left."""

    def __init__(
        self,
        bands: int = 24,
        size: int = SIZE,
        bar_width: int | None = None,
        palette: str = "hue",
        contrast: str = "high",
    ):
        self.size = size
        self.bands = bands
        self.bar_width = bar_width
        self._heat = _SPECTROGRAM_PALETTES.get(palette, _SPECTROGRAM_PALETTES["hue"])
        self._gamma = _CONTRAST_GAMMA.get(contrast, _CONTRAST_GAMMA["high"])
        self._buf = np.zeros((size, size, 3), dtype=np.uint8)
        self._src = np.arange(bands)
        if bar_width is not None:
            if bar_width < 1 or size % bar_width != 0:
                raise ValueError(f"spectrogram bar_width must evenly divide {size}")
            self._render_bands = size // bar_width
            self._dst = np.linspace(0, bands - 1, self._render_bands)
        else:
            self._render_bands = size
            self._dst = np.linspace(0, bands - 1, size)  # stretch bands → panel rows

    def render(self, levels: np.ndarray, peaks: np.ndarray) -> bytes:
        col = np.clip(np.interp(self._dst, self._src, levels), 0.0, 1.0)
        col = np.power(col, self._gamma)
        rgb = self._heat[(col * 255).astype(int)]     # color by intensity, independent of frequency row
        if self.bar_width is not None:
            rgb = np.repeat(rgb, self.bar_width, axis=0)
        self._buf[:, :-1] = self._buf[:, 1:]     # scroll left
        self._buf[:, -1] = rgb[::-1]             # newest column on the right, low freq at bottom
        return self._buf.tobytes()


def make_visualizer(mode: str, bands: int, size: int = SIZE, **kwargs: object) -> Visualizer:
    modes = {"bars": SpectrumBars, "vu": VUMeter, "spectrogram": Spectrogram}
    if mode not in modes:
        raise ValueError(f"unknown visualizer mode {mode!r} (choose {', '.join(modes)})")
    if mode == "spectrogram":
        bar_width = kwargs.get("bar_width")
        palette = str(kwargs.get("palette", "hue"))
        contrast = str(kwargs.get("contrast", "high"))
        return Spectrogram(
            bands=bands,
            size=size,
            bar_width=int(str(bar_width)) if bar_width is not None else None,
            palette=palette,
            contrast=contrast,
        )
    if mode == "bars":
        bar_width = kwargs.get("bar_width")
        gap = kwargs.get("gap", 0)
        return SpectrumBars(
            bands=bands,
            size=size,
            gap=int(str(gap)),
            bar_width=int(str(bar_width)) if bar_width is not None else None,
        )
    return modes[mode](bands=bands, size=size)
