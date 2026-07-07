"""Audio sources — anything that yields mono float32 PCM blocks in [-1, 1].

DeviceAudioSource captures from a PortAudio input (a Scarlett loopback channel,
BlackHole, or a mic); SyntheticSource generates deterministic tones so the DSP
can be tested without hardware. New sources (a network feed, a file) only need
``blocks()`` + ``close()``.
"""

import subprocess
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np


class AudioSource(Protocol):
    samplerate: int

    def blocks(self) -> Iterator[np.ndarray]: ...  # mono float32, length ~= blocksize
    def close(self) -> None: ...


def list_input_devices() -> list[tuple[int, str]]:
    """(index, name) for every device with input channels — for `--list-devices`."""
    import sounddevice as sd

    return [
        (i, d["name"])
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


def _resolve_device(device: str | int | None) -> str | int | None:
    if device is None:
        return None
    if isinstance(device, int):
        return device
    return int(device) if device.isdigit() else device  # index or name substring


class DeviceAudioSource:
    """Captures from a PortAudio input device, downmixed to mono."""

    def __init__(
        self,
        device: str | int | None = None,
        samplerate: int = 44100,
        blocksize: int = 1024,
        channels: int | None = None,
    ):
        import sounddevice as sd

        self.device = _resolve_device(device)
        self.samplerate = samplerate
        self.blocksize = blocksize
        if channels is None:
            info = sd.query_devices(self.device, "input")
            channels = min(2, int(info["max_input_channels"])) or 1
        self.channels = channels
        self._stream = None

    def blocks(self) -> Iterator[np.ndarray]:
        import sounddevice as sd

        self._stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            dtype="float32",
        )
        self._stream.start()
        while True:
            data, _overflowed = self._stream.read(self.blocksize)  # (n, channels)
            yield data.mean(axis=1) if self.channels > 1 else data[:, 0]

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class FileAudioSource:
    """Decodes an audio file to mono float32 blocks via ffmpeg.

    Yields as fast as it can (not real-time paced) — ideal for rendering a
    visualization to a video offline, or previewing a track without the panel.
    Handles anything ffmpeg reads (webm/opus, m4a, mp3, wav, …).
    """

    def __init__(
        self,
        path: str | Path,
        samplerate: int = 44100,
        blocksize: int = 1024,
        start: float = 0.0,
        duration: float | None = None,
    ):
        self.path = str(path)
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.start = start
        self.duration = duration
        self._audio: np.ndarray | None = None

    def _decode(self) -> np.ndarray:
        cmd = ["ffmpeg", "-v", "error"]
        if self.start:
            cmd += ["-ss", str(self.start)]
        cmd += ["-i", self.path]
        if self.duration:
            cmd += ["-t", str(self.duration)]
        cmd += ["-ac", "1", "-ar", str(self.samplerate), "-f", "f32le", "-"]
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype=np.float32)

    def blocks(self) -> Iterator[np.ndarray]:
        if self._audio is None:
            self._audio = self._decode()
        n = self.blocksize
        for i in range(0, len(self._audio) - n + 1, n):
            yield self._audio[i : i + n]

    def close(self) -> None:
        self._audio = None


class SyntheticSource:
    """Deterministic sine tone(s) — for tests and offline demos, no hardware."""

    def __init__(
        self,
        freqs: float | list[float] = 1000.0,
        samplerate: int = 44100,
        blocksize: int = 1024,
        blocks: int = 8,
        amplitude: float = 0.5,
    ):
        self.freqs = [freqs] if isinstance(freqs, (int, float)) else list(freqs)
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._n = blocks
        self._amp = amplitude

    def blocks(self) -> Iterator[np.ndarray]:
        pos = 0
        for _ in range(self._n):
            t = (np.arange(self.blocksize) + pos) / self.samplerate
            sig = np.zeros(self.blocksize, dtype=np.float32)
            for f in self.freqs:
                sig += self._amp * np.sin(2 * np.pi * f * t).astype(np.float32)
            yield sig / max(1, len(self.freqs))
            pos += self.blocksize

    def close(self) -> None:
        pass
