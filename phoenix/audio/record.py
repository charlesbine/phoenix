"""Record 64x64 RGB frames to a video via ffmpeg.

Lets you preview a visualizer against a file without the panel — the frames pipe
straight into ffmpeg, upscaled with nearest-neighbor so the pixels stay crisp.
"""

import subprocess
from pathlib import Path


class FrameRecorder:
    def __init__(self, path: str | Path, fps: float = 43.0, size: int = 64, scale: int = 8):
        out = size * scale
        self._proc = subprocess.Popen(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size}x{size}",
                "-r", f"{fps:.3f}", "-i", "-",
                "-vf", f"scale={out}:{out}:flags=neighbor",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(path),
            ],
            stdin=subprocess.PIPE,
        )

    def add(self, rgb: bytes) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(rgb)

    def close(self) -> None:
        if self._proc.stdin is not None:
            self._proc.stdin.close()
        self._proc.wait()
