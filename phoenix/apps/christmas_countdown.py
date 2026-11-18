"""Animated Christmas countdown for the 64×64 Phoenix panel."""

from datetime import date, datetime
from math import sin, tau
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from phoenix.settings import Settings

# A three-by-five bitmap font stays legible at the matrix's native resolution.
GLYPHS = {
    "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (7, 1, 7, 4, 7),
    "3": (7, 1, 7, 1, 7), "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7),
    "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 2, 2), "8": (7, 5, 7, 5, 7),
    "9": (7, 5, 7, 1, 7), "A": (2, 5, 7, 5, 5), "C": (7, 4, 4, 4, 7),
    "D": (6, 5, 5, 5, 6), "E": (7, 4, 6, 4, 7), "F": (7, 4, 6, 4, 4),
    "H": (5, 5, 7, 5, 5), "I": (7, 2, 2, 2, 7), "L": (4, 4, 4, 4, 7),
    "M": (5, 7, 7, 5, 5), "R": (6, 5, 6, 5, 5), "S": (7, 4, 7, 1, 7),
    "T": (7, 2, 2, 2, 2), "Y": (5, 5, 2, 2, 2), "!": (2, 2, 2, 0, 2),
    " ": (0, 0, 0, 0, 0),
}
GOLD = "#ffce73"
CREAM = "#fff0c7"
RED = "#b82e45"

SNOW_FRAMES = 32
FRAME_MS = 125
INTERLUDE_FRAMES = 40
FINAL_PAUSE = 95
SNOW = "#b9dced"


def _text(draw: ImageDraw.ImageDraw, label: str, y: int, color: str, scale: int = 1) -> None:
    width = (4 * len(label) - 1) * scale
    left = (64 - width) // 2
    for index, letter in enumerate(label):
        for row, bits in enumerate(GLYPHS[letter]):
            for column in range(3):
                if bits & (4 >> column):
                    x = left + (4 * index + column) * scale
                    top = y + row * scale
                    draw.rectangle((x, top, x + scale - 1, top + scale - 1), fill=color)


def _tree(draw: ImageDraw.ImageDraw, x: int, y: int, tick: int) -> None:
    draw.rectangle((x - 1, y + 16, x + 1, y + 19), fill="#895044")
    for offset, width, green in ((0, 4, "#489668"), (4, 6, "#338666"), (8, 8, "#237058")):
        top = y + offset
        draw.polygon(((x, top), (x - width, top + 8), (x + width, top + 8)), fill=green)
        draw.line((x, top, x - width + 1, top + 7), fill="#65b38a")
    draw.line((x - 1, y - 2, x + 1, y - 2), fill=GOLD)
    draw.line((x, y - 3, x, y - 1), fill=GOLD)
    for index, (dx, dy) in enumerate(((-1, 5), (2, 8), (-3, 11), (4, 13), (0, 15))):
        colors = (CREAM, "#ef6071", "#78cbe3")
        draw.point((x + dx, y + dy), fill=colors[(tick // 8 + index) % len(colors)])


def _gift(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, paper: str, lift: int = 0) -> None:
    draw.rectangle((x, y + 1, x + width - 1, 60), fill=paper)
    center = x + width // 2
    draw.line((center, y + 1, center, 60), fill=GOLD)
    lid = y - lift
    draw.line((x - 1, lid, x + width, lid), fill=paper)
    draw.point((center, lid - 1), fill=GOLD)
    draw.line((center - 2, lid - 2, center + 2, lid - 2), fill=GOLD)


def _frame(days: int, tick: int, gift_lift: int = 0) -> Image.Image:
    image = Image.new("RGB", (64, 64), "#10192e")
    draw = ImageDraw.Draw(image)
    rng = Random(25)
    for index in range(35):
        start_x, start_y = rng.randrange(64), rng.randrange(64)
        y = (start_y + tick * 2) % 64
        displacement = (0, 1, 2, 1)[((y // 8) + index) % 4]
        x = (start_x + displacement) % 64
        if y < 57 and (x < 13 or x > 50 or y < 10):
            draw.point((x, y), fill=SNOW if index % 4 == 0 else "#54748c")

    draw.polygon(((0, 59), (10, 56), (20, 58), (37, 56), (50, 58), (63, 55), (63, 63), (0, 63)),
                 fill="#638ba6")
    draw.line((0, 63, 16, 61, 28, 63, 42, 61, 63, 62), fill="#a9cbdf")
    _tree(draw, 10, 40, tick)
    _tree(draw, 54, 40, tick + 8)
    _gift(draw, 22, 55, 8, RED)
    _gift(draw, 32, 55, 10, "#397c69", lift=gift_lift)

    draw.polygon(((5, 10), (58, 10), (55, 14), (58, 18), (5, 18), (8, 14)), fill=RED)
    draw.line((9, 10, 54, 10), fill="#ef6675")
    _text(draw, "CHRISTMAS", 12, CREAM)
    if days == 0:
        _text(draw, "MERRY", 24, GOLD, scale=2)
        _text(draw, "CHRISTMAS!", 39, CREAM)
    else:
        _text(draw, str(days), 22, GOLD, scale=4)
        _text(draw, "DAY LEFT" if days == 1 else "DAYS LEFT", 44, CREAM)
    return image


def _sleigh(days: int, tick: int, snow_tick: int) -> Image.Image:
    image = _frame(days, snow_tick)
    draw = ImageDraw.Draw(image)
    x = -30 + tick * 96 // (INTERLUDE_FRAMES - 1)
    y = (tick // 4) % 2
    # Runners, Santa's coat and hat, and his reins.
    draw.line((x + 1, y + 8, x + 13, y + 8, x + 16, y + 6), fill=GOLD)
    draw.polygon(((x, y + 4), (x + 3, y + 6), (x + 12, y + 6), (x + 14, y + 4),
                  (x + 14, y + 7), (x + 3, y + 7)), fill="#e24754")
    draw.rectangle((x + 7, y + 3, x + 10, y + 5), fill="#e24754")
    draw.rectangle((x + 8, y + 1, x + 11, y + 2), fill=CREAM)
    draw.line((x + 7, y, x + 10, y), fill="#ff6771")
    draw.line((x + 11, y + 4, x + 23, y + 4), fill="#c28058")
    # Reindeer with alternating legs, antlers and a red nose.
    draw.rectangle((x + 20, y + 4, x + 26, y + 5), fill="#e0a068")
    draw.rectangle((x + 25, y + 2, x + 28, y + 4), fill="#e0a068")
    draw.line((x + 25, y + 2, x + 24, y, x + 23, y), fill=GOLD)
    draw.line((x + 27, y + 2, x + 27, y), fill=GOLD)
    stride = 1 if tick % 4 < 2 else -1
    draw.line((x + 21, y + 5, x + 21 - stride, y + 7), fill="#e0a068")
    draw.line((x + 25, y + 5, x + 25 + stride, y + 7), fill="#e0a068")
    draw.point((x + 29, y + 3), fill="#ff6771")
    draw.point((x - 2, y + 6), fill=GOLD)
    return image


def _gift_pop(days: int, tick: int, snow_tick: int) -> Image.Image:
    progress = tick / (INTERLUDE_FRAMES - 1)
    lift = round(4 * sin(tau * progress / 2))
    image = _frame(days, snow_tick, gift_lift=lift)
    draw = ImageDraw.Draw(image)
    for index, spread in enumerate((-16, -11, -6, 6, 11, 16)):
        age = progress - index * 0.035
        if 0 < age < 0.70:
            x = 37 + round(spread * age / 0.55)
            y = 55 - round(6 * sin(tau * age / 1.4))
            draw.point((x, y), fill=(GOLD, CREAM, "#ff7880")[index % 3])
            if index % 2 == 0 and age < 0.42:
                draw.point((x, y + 1), fill=GOLD)
    return image


def _shooting_star(days: int, tick: int, snow_tick: int) -> Image.Image:
    image = _frame(days, snow_tick)
    draw = ImageDraw.Draw(image)
    x = -14 + 83 * tick // (INTERLUDE_FRAMES - 1)
    y = 2 + max(0, x) // 13
    for offset, color in ((14, "#604966"), (9, "#a57368"), (5, GOLD)):
        draw.line((x - offset, max(0, y - offset // 5), x - offset + 4, y - offset // 9), fill=color)
    draw.line((x - 2, y, x + 2, y), fill=GOLD)
    draw.line((x, y - 2, x, y + 2), fill=GOLD)
    draw.point((x, y), fill=CREAM)
    return image


# One interlude near startup, then roughly two minutes between highlights.
INTERLUDES = ((6, _sleigh), (125, _gift_pop), (155, _shooting_star))
PLAYBACK_SECONDS = FINAL_PAUSE + sum(
    pause + FRAME_MS * INTERLUDE_FRAMES // 1000 for pause, _ in INTERLUDES
)


def _timeline(days: int, scale: int) -> list[Image.Image]:
    def resize(frame: Image.Image) -> Image.Image:
        return frame.resize((64 * scale, 64 * scale), Image.Resampling.NEAREST) if scale > 1 else frame

    idle = [resize(_frame(days, tick)) for tick in range(SNOW_FRAMES)]
    frames: list[Image.Image] = []

    def add_pause(seconds: int) -> None:
        start = len(frames)
        end = start + seconds * 1000 // FRAME_MS
        frames.extend(idle[tick % SNOW_FRAMES] for tick in range(start, end))

    for pause, effect in INTERLUDES:
        add_pause(pause)
        start = len(frames)
        frames.extend(resize(effect(days, tick, (start + tick) % SNOW_FRAMES))
                      for tick in range(INTERLUDE_FRAMES))
    add_pause(FINAL_PAUSE)
    return frames


def _save_animation(frames: list[Image.Image], output: Path) -> None:
    # Phoenix's display loop can open the previous render while this one is encoding.
    with TemporaryDirectory(dir=output.parent) as temp:
        staging = Path(temp) / output.name
        frames[0].save(staging, "WEBP", save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, loop=0, lossless=True)
        staging.replace(output)


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    today = datetime.now(ZoneInfo(config.get("$tz", "America/New_York"))).date()
    christmas = date.fromisoformat(config.get("christmas_date", f"{today.year}-12-25"))
    days = max(0, (christmas - today).days)
    _save_animation(_timeline(days, 1), output)
    _save_animation(_timeline(days, settings.magnification), output_large)
