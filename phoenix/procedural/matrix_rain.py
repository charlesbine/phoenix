"""Digital rain in a 64×64 LED grid, with an optional live clock face."""

from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from random import Random
import tempfile

from PIL import Image, ImageDraw

from phoenix.display.sink import MATRIX_SIZE

# Three-pixel-wide terminal glyphs; each tuple packs five scanlines.
GLYPHS = (
    (7, 1, 3, 1, 2), (2, 7, 2, 2, 3), (5, 5, 1, 2, 4),
    (7, 1, 1, 1, 7), (2, 5, 7, 5, 5), (7, 2, 7, 2, 2),
    (1, 2, 4, 2, 1), (4, 5, 7, 1, 2), (7, 4, 6, 4, 7),
    (5, 2, 5, 0, 2), (3, 2, 6, 2, 2), (6, 5, 6, 4, 4),
    (4, 4, 5, 5, 7), (2, 0, 7, 1, 2), (7, 5, 5, 5, 7),
    (5, 5, 7, 1, 1), (2, 7, 1, 1, 2), (7, 2, 4, 2, 7),
)
DIGITS = (
    (14, 17, 19, 21, 25, 17, 14), (4, 12, 4, 4, 4, 4, 14),
    (14, 17, 1, 2, 4, 8, 31), (30, 1, 1, 14, 1, 1, 30),
    (2, 6, 10, 18, 31, 2, 2), (31, 16, 16, 30, 1, 1, 30),
    (6, 8, 16, 30, 17, 17, 14), (31, 1, 2, 4, 8, 8, 8),
    (14, 17, 17, 14, 17, 17, 14), (14, 17, 17, 15, 1, 2, 12),
)
TRAIL = ((142, 255, 178), (16, 180, 71), (4, 114, 45), (1, 72, 31),
         (0, 45, 22), (0, 28, 15), (0, 17, 9))


def _bitmap(rows: tuple[int, ...], width: int) -> Image.Image:
    mask = Image.new("L", (width, len(rows)))
    mask.putdata([255 if row & (1 << bit) else 0
                  for row in rows for bit in reversed(range(width))])
    return mask


_GLYPHS = tuple(_bitmap(rows, 3) for rows in GLYPHS)
# Full-size code symbols use the numeral stroke width on the clock plates.
_CODE_ROWS = (
    (0, 31, 1, 5, 4, 8, 16), (4, 31, 17, 1, 2, 4, 8),
    (2, 31, 6, 10, 18, 2, 6), (8, 31, 9, 9, 9, 17, 2),
    (4, 31, 4, 31, 4, 2, 2), (0, 14, 2, 2, 4, 8, 31),
    (0, 31, 1, 2, 4, 10, 17), (0, 21, 21, 1, 2, 4, 8),
    (0, 10, 31, 10, 31, 10, 0), (0, 4, 21, 14, 21, 4, 0),
    (0, 2, 4, 8, 4, 2, 0), (0, 8, 4, 2, 4, 8, 0),
    (0, 14, 8, 8, 8, 14, 0), (0, 31, 0, 4, 0, 31, 0),
    (0, 1, 2, 4, 8, 16, 0), (0, 8, 16, 14, 1, 2, 0),
)
_CODE = tuple(_bitmap(rows, 5).resize((10, 21), Image.Resampling.NEAREST) for rows in _CODE_ROWS)
_DIGITS = tuple(_bitmap(rows, 5).resize((10, 21), Image.Resampling.NEAREST) for rows in DIGITS)
DIGIT_X = (4, 17, 35, 48)
DECODE_MS = 2200
GLYPH_MS = 80
SPEEDS = {str(value): float(value) for value in (0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8)}
# Density changes the number of empty cells between trails on a column.
GAP_SCALE = {"sparse": 2.0, "normal": 1.0, "dense": 0.5}
SETTINGS_SCHEMA = [
    {"type": "dropdown", "id": "rain_speed", "name": "Rain speed", "default": "1",
     "options": [{"value": speed, "display": f"{speed}×"} for speed in SPEEDS]},
    {"type": "dropdown", "id": "rain_density", "name": "Rain density", "default": "normal",
     "options": [{"value": density, "display": density.title()} for density in GAP_SCALE]},
]


@lru_cache(maxsize=4)
def _decode_sequence(minute: int, slot: int) -> list[Image.Image]:
    # Repeated draws of a single tick must show the same glyph on a slower player.
    rng = Random(minute * 4 + slot)
    return rng.sample(_CODE, len(_CODE))


class MatrixRain:
    def __init__(self, seed: int = 11) -> None:
        rng = Random(seed)
        # Different gaps, trail lengths and rates keep columns out of lockstep.
        self.columns = [
            (rng.uniform(1.4, 4.6), rng.randrange(20), rng.randint(13, 24),
             rng.randint(4, len(TRAIL)), rng.choices(_GLYPHS, k=67))
            for _ in range(MATRIX_SIZE[0] // 4)
        ]

        self._speed = 1.0
        self._gap_scale = 1.0
        self._extra_fall = [0.0] * len(self.columns)
        self._last_clock_frame: float | None = None

    def configure(self, config: dict[str, str]) -> None:
        self._speed = SPEEDS.get(config.get("rain_speed", "1"), 1.0)
        self._gap_scale = GAP_SCALE.get(config.get("rain_density", "normal"), 1.0)

    def frame(self, elapsed: float, local_time: datetime | None = None) -> Image.Image:
        image = Image.new("RGB", MATRIX_SIZE)
        decoding = {}
        if local_time is not None:
            digits = local_time.strftime("%H%M")
            ms_left = (60 - local_time.second) * 1000 - local_time.microsecond // 1000
            if ms_left <= DECODE_MS:
                # Step along the UTC timeline to handle midnight and DST folds or gaps.
                next_minute = datetime.fromtimestamp(local_time.timestamp() + 60, local_time.tzinfo)
                glyph_index = ((DECODE_MS - ms_left) // GLYPH_MS) % len(_CODE)
                minute = int(next_minute.timestamp()) // 60
                for slot, (old, new) in enumerate(zip(digits, next_minute.strftime("%H%M"))):
                    if old != new:
                        decoding[slot] = _decode_sequence(minute, slot)[glyph_index]
            # Advance just the streams crossing a decoding slot, keeping their new
            # positions when the clock locks. Cap the step on re-entry from rotation.
            if decoding and self._last_clock_frame is not None:
                dt = min(max(0, elapsed - self._last_clock_frame), 0.5, (DECODE_MS - ms_left) / 1000)
                for slot in decoding:
                    for col in range(len(self.columns)):
                        if DIGIT_X[slot] <= col * 4 + 1 < DIGIT_X[slot] + 12:
                            self._extra_fall[col] += dt
            self._last_clock_frame = elapsed

        for col, (rate, offset, period, length, symbols) in enumerate(self.columns):
            t = elapsed + self._extra_fall[col] if local_time is not None else elapsed
            tick = int(t * rate * self._speed) + offset
            period = length + round((period - length) * self._gap_scale)
            cycle, head = divmod(tick, period)
            for age in range(length):
                row = (head - age) % period
                y = row * 6 - (col % 3)
                if y >= image.height:
                    continue
                # A glyph stays on its cell as the tail fades, until the next pass.
                generation = cycle - (age > head)
                glyph = symbols[(row + generation * 13) % len(symbols)]
                image.paste(TRAIL[age], (col * 4, y), glyph)
        if local_time is not None:
            _draw_time(image, digits, decoding)
        return image


def _draw_time(image: Image.Image, digits: str, decoding: dict[int, Image.Image]) -> None:
    draw = ImageDraw.Draw(image)
    y = (image.height - 23) // 2
    for slot, (x, digit) in enumerate(zip(DIGIT_X, digits)):
        draw.rectangle((x, y, x + 11, y + 22), fill="black")
        if slot in decoding:
            image.paste((199, 255, 207), (x + 1, y + 1), decoding[slot])
        else:
            image.paste((235, 255, 241), (x + 1, y + 1), _DIGITS[int(digit)])
    draw.rectangle((30, y, 33, y + 22), fill="black")
    for dy in (7, 15):
        draw.rectangle((31, y + dy, 32, y + dy + 1), fill=(160, 222, 177))


def render_preview(
    config: dict[str, str],
    output: Path,
    output_large: Path,
    *,
    magnification: int = 2,
    local_time: datetime | None = None,
    duration_seconds: float = 3.0,
    fps: int = 15,
) -> None:
    """Render an animated WebP preview (64x64 and magnified) using current rain settings."""
    rain = MatrixRain()
    rain.configure(config)
    count = max(1, int(round(duration_seconds * fps)))
    frame_ms = max(20, round(1000 / fps))
    frames = [
        rain.frame(
            i / fps,
            local_time + timedelta(seconds=i / fps) if local_time is not None else None,
        )
        for i in range(count)
    ]
    scale = max(1, magnification)
    large_size = (MATRIX_SIZE[0] * scale, MATRIX_SIZE[1] * scale)
    large_frames = (
        frames
        if scale == 1
        else [frame.resize(large_size, Image.Resampling.NEAREST) for frame in frames]
    )

    for dest, seq in ((output, frames), (output_large, large_frames)):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".webp", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            seq[0].save(
                tmp_path,
                "WEBP",
                save_all=True,
                append_images=seq[1:],
                duration=frame_ms,
                loop=0,
                lossless=True,
            )
            tmp_path.chmod(0o644)
            tmp_path.replace(dest)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
