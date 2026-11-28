"""Digital rain in a 64×64 LED grid, with an optional live clock face."""

from datetime import datetime
from functools import lru_cache
from random import Random

from PIL import Image, ImageDraw, ImageFilter

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


class MatrixRain:
    def __init__(self, seed: int = 11) -> None:
        rng = Random(seed)
        # Different gaps, trail lengths and rates keep columns out of lockstep.
        self.columns = [
            (rng.uniform(1.4, 4.6), rng.randrange(20), rng.randint(13, 24),
             rng.randint(4, len(TRAIL)), rng.choices(_GLYPHS, k=67))
            for _ in range(MATRIX_SIZE[0] // 4)
        ]

    def frame(self, elapsed: float, local_time: datetime | None = None) -> Image.Image:
        image = Image.new("RGB", MATRIX_SIZE)
        for col, (rate, offset, period, length, symbols) in enumerate(self.columns):
            tick = int(elapsed * rate) + offset
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
            _draw_time(image, local_time)
        return image


@lru_cache(maxsize=10)
def _digit_layers(digit: str) -> tuple[Image.Image, Image.Image]:
    # The dark one-pixel outline preserves the shape when rain passes behind it.
    mask = Image.new("L", (12, 23))
    glyph = _bitmap(DIGITS[int(digit)], 5).resize((10, 21), Image.Resampling.NEAREST)
    mask.paste(glyph, (1, 1))
    return mask, mask.filter(ImageFilter.MaxFilter(3))


def _draw_time(image: Image.Image, now: datetime) -> None:
    current = now.strftime("%H%M")
    # Work in elapsed seconds so DST jumps decode from the actual preceding minute.
    previous = current
    reveal = 23
    if now.second == 0 and now.microsecond < 750_000:
        previous = datetime.fromtimestamp(now.timestamp() - 60, now.tzinfo).strftime("%H%M")
        reveal = 23 * now.microsecond // 750_000
    y = (image.height - 23) // 2
    for x, old, new in zip((4, 17, 35, 48), previous, current):
        mask, outline = _digit_layers(new)
        if old != new and reveal < 23:
            old_mask, old_outline = _digit_layers(old)
            mask, outline = mask.copy(), outline.copy()
            remaining = (0, reveal, 12, 23)
            mask.paste(old_mask.crop(remaining), (0, reveal))
            outline.paste(old_outline.crop(remaining), (0, reveal))
        image.paste((0, 10, 4), (x, y), outline)
        image.paste((165, 255, 194), (x, y), mask)
        if old != new and reveal < 23:
            ImageDraw.Draw(image).line((x + 1, y + reveal, x + 10, y + reveal), fill=(217, 255, 231))
    draw = ImageDraw.Draw(image)
    for dy in (7, 15):
        draw.rectangle((31, y + dy, 32, y + dy + 1), fill=(74, 205, 120))
