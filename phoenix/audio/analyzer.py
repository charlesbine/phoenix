"""Spectrum analysis — a PCM block becomes N log-spaced band levels in [0, 1].

Windowed rFFT → per-band peak magnitude → dB → normalized against a noise floor,
then attack/release smoothing (fast rise, slow fall, like a real VU) and a
decaying peak-hold for the bar caps. Pure numpy, so it's deterministic and
testable with synthetic tones.
"""

import numpy as np


class SpectrumAnalyzer:
    def __init__(
        self,
        samplerate: int = 44100,
        fft_size: int = 1024,
        bands: int = 24,
        fmin: float = 40.0,
        fmax: float = 16000.0,
        floor_db: float = -70.0,
        noise_gate: float = 0.0,
        attack: float = 0.55,   # fraction toward a rising target per block
        release: float = 0.15,  # slower fall
        peak_decay: float = 0.015,
        tilt: float = 3.0,      # dB/octave lift on highs (pink-noise comp) — evens the spectrum
        gain_db: float = 6.0,   # overall sensitivity bump
        tilt_pivot: float = 1000.0,
    ):
        self.samplerate = samplerate
        self.fft_size = fft_size
        self.bands = bands
        self.floor_db = floor_db
        self.noise_gate = float(np.clip(noise_gate, 0.0, 0.95))
        self.attack = attack
        self.release = release
        self.peak_decay = peak_decay
        self.gain_db = gain_db

        self._window = np.hanning(fft_size).astype(np.float32)
        freqs = np.fft.rfftfreq(fft_size, 1.0 / samplerate)
        edges = np.logspace(np.log10(fmin), np.log10(min(fmax, samplerate / 2)), bands + 1)
        # Precompute the rFFT bin indices that fall in each band.
        self._bins: list[np.ndarray] = []
        for b in range(bands):
            idx = np.where((freqs >= edges[b]) & (freqs < edges[b + 1]))[0]
            if idx.size == 0:  # band narrower than a bin — snap to the nearest
                idx = np.array([int(np.argmin(np.abs(freqs - (edges[b] + edges[b + 1]) / 2)))])
            self._bins.append(idx)

        # Per-band tilt: lift highs, cut lows, pivoting at ~1kHz so music's
        # natural bass-heavy 1/f rolloff doesn't leave the treble bars stubby.
        centers = np.sqrt(edges[:-1] * edges[1:])
        self._tilt_db = (tilt * np.log2(centers / tilt_pivot)).astype(np.float32)

        self._levels = np.zeros(bands, dtype=np.float32)
        self._peaks = np.zeros(bands, dtype=np.float32)

    def process(self, block: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """One PCM block → (levels, peaks), each length ``bands`` in [0, 1]."""
        x = np.asarray(block, dtype=np.float32).ravel()
        if x.size < self.fft_size:
            x = np.pad(x, (0, self.fft_size - x.size))
        elif x.size > self.fft_size:
            x = x[: self.fft_size]

        spec = np.abs(np.fft.rfft(x * self._window)) / self.fft_size
        raw = np.empty(self.bands, dtype=np.float32)
        for b, idx in enumerate(self._bins):
            mag = float(spec[idx].max())  # peak-in-band is punchier than mean
            db = 20.0 * np.log10(mag + 1e-9) + self._tilt_db[b] + self.gain_db
            raw[b] = np.clip((db - self.floor_db) / (-self.floor_db), 0.0, 1.0)

        if self.noise_gate > 0.0:
            raw = np.where(raw < self.noise_gate, 0.0, (raw - self.noise_gate) / (1.0 - self.noise_gate))

        # Attack/release: rise fast, fall slow.
        coeff = np.where(raw > self._levels, self.attack, self.release).astype(np.float32)
        self._levels += coeff * (raw - self._levels)
        # Peak-hold with slow decay for the bar caps.
        self._peaks = np.maximum(self._peaks - self.peak_decay, self._levels)
        return self._levels.copy(), self._peaks.copy()

    def reset(self) -> None:
        self._levels[:] = 0.0
        self._peaks[:] = 0.0
