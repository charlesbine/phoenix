"""Pure-Python Pillow renderer for Phoenix 64x64 programmatic dashboard panels.

Renders all 5 panel layouts (big_number, sparkline, multi_stat, key_value, marquee)
with crisp bitmap pixel typography, shaded sparkline area fills, dark slate hardware
tiles, status pips, and delta pills — with zero loopback HTTP or pixlet dependency.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

# Hardware-instrument palette defaults (high contrast on 64x64 HUB75 / WLED)
BG_CANVAS: RGB = (0, 0, 0)
BG_HEADER: RGB = (15, 21, 34)       # #0f1522
BG_CARD: RGB = (10, 15, 25)         # #0a0f19
BG_CARD_ALT: RGB = (6, 9, 16)       # #060910
BORDER_SUBTLE: RGB = (28, 40, 62)   # #1c283e
BORDER_DIM: RGB = (20, 29, 46)      # #141d2e
GRID_LINE: RGB = (24, 35, 54)       # #182336

DEFAULT_ACCENT: RGB = (255, 142, 60)     # Phoenix ember #ff8e3c
DEFAULT_CYAN: RGB = (91, 206, 250)       # #5bcefa
DEFAULT_EMERALD: RGB = (46, 229, 141)    # #2ee58d
DEFAULT_CORAL: RGB = (255, 94, 87)       # #ff5e57
DEFAULT_TEXT: RGB = (244, 247, 252)      # #f4f7fc
DEFAULT_TITLE: RGB = (168, 184, 208)     # #a8b8d0
DEFAULT_LABEL: RGB = (122, 140, 168)     # #7a8ca8
DEFAULT_MUTED: RGB = (92, 109, 136)      # #5c6d88


def parse_hex_color(raw: object, fallback: RGB = DEFAULT_TEXT) -> RGB:
    """Parse #RGB or #RRGGBB hex string into an (R, G, B) tuple."""
    if not isinstance(raw, str):
        return fallback
    s = raw.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return fallback


def blend(fg: RGB, bg: RGB, alpha: float) -> RGB:
    """Alpha-blend foreground RGB over background RGB."""
    a = max(0.0, min(1.0, alpha))
    return (
        int(round(fg[0] * a + bg[0] * (1.0 - a))),
        int(round(fg[1] * a + bg[1] * (1.0 - a))),
        int(round(fg[2] * a + bg[2] * (1.0 - a))),
    )


def _brighten(color: RGB, amount: float = 0.45) -> RGB:
    return blend((255, 255, 255), color, amount)


def _dim(color: RGB, factor: float = 0.45) -> RGB:
    return blend(color, (0, 0, 0), factor)


# ---------------------------------------------------------------------------
# Crisp bitmap pixel fonts (zero blurry TrueType anti-aliasing)
# ---------------------------------------------------------------------------

# 3x5 micro pixel font (proportional width 1..3px, height 5px).
# Inspired by tom-thumb for razor-sharp LED headers, labels, and micro badges.
FONT_3X5: dict[str, tuple[str, ...]] = {
    " ": ("..", "..", "..", "..", ".."),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("#", "#", "#", "#", "#"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#..#", "####", "#..#", "#..#", "#..#"),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", "##.", "..#"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#..#", "#..#", "#..#", "####", "#..#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    # Lowercase for readable units (ms, d, h, k, etc.)
    "a": ("...", "##.", ".##", "#.#", "###"),
    "b": ("#..", "#..", "##.", "#.#", "##."),
    "c": ("...", ".##", "#..", "#..", ".##"),
    "d": ("..#", "..#", ".##", "#.#", ".##"),
    "e": ("...", ".#.", "###", "#..", ".##"),
    "f": (".##", "#..", "##.", "#..", "#.."),
    "g": (".##", "#.#", ".##", "..#", "##."),
    "h": ("#..", "#..", "##.", "#.#", "#.#"),
    "i": ("#", ".", "#", "#", "#"),
    "j": (".#", "..", ".#", ".#", "#."),
    "k": ("#..", "#.#", "##.", "#.#", "#.#"),
    "l": ("#.", "#.", "#.", "#.", ".#"),
    "m": ("...", "###", "###", "#.#", "#.#"),
    "n": ("...", "##.", "#.#", "#.#", "#.#"),
    "o": ("...", ".#.", "#.#", "#.#", ".#."),
    "p": ("...", "##.", "#.#", "##.", "#.."),
    "q": ("...", ".##", "#.#", ".##", "..#"),
    "r": ("...", ".##", "#..", "#..", "#.."),
    "s": ("...", ".##", ".#.", "..#", "##."),
    "t": (".#.", "###", ".#.", ".#.", "..#"),
    "u": ("...", "#.#", "#.#", "#.#", "###"),
    "v": ("...", "#.#", "#.#", "#.#", ".#."),
    "w": ("...", "#.#", "###", "###", "#.#"),
    "x": ("...", "#.#", ".#.", "#.#", "#.#"),
    "y": ("...", "#.#", ".##", "..#", "##."),
    "z": ("...", "###", ".#.", "#..", "###"),
    # Symbols & punctuation
    ".": (".", ".", ".", ".", "#"),
    ",": (".", ".", ".", "#", "#"),
    ":": (".", "#", ".", "#", "."),
    ";": (".", "#", ".", "#", "#"),
    "!": ("#", "#", "#", ".", "#"),
    "?": ("##.", "..#", ".#.", "...", ".#."),
    "-": ("...", "...", "###", "...", "..."),
    "—": ("...", "...", "###", "...", "..."),
    "–": ("...", "...", "###", "...", "..."),
    "_": ("...", "...", "...", "...", "###"),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "=": ("...", "###", "...", "###", "..."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    "\\": ("#..", "#..", ".#.", "..#", "..#"),
    "%": ("#.#", "..#", ".#.", "#..", "#.#"),
    "$": (".#.", "###", "##.", ".##", "###"),
    "€": (".##", "###", "#..", "###", ".##"),
    "£": (".##", "#..", "###", "#..", "###"),
    "°": (".#.", "#.#", ".#.", "...", "..."),
    "'": ("#", "#", ".", ".", "."),
    '"': ("#.#", "#.#", "...", "...", "..."),
    "(": (".#", "#.", "#.", "#.", ".#"),
    ")": ("#.", ".#", ".#", ".#", "#."),
    "[": ("##", "#.", "#.", "#.", "##"),
    "]": ("##", ".#", ".#", ".#", "##"),
    "#": ("#.#", "###", "#.#", "###", "#.#"),
    "@": (".##", "#.#", "###", "#..", ".##"),
    "&": (".#.", "#.#", ".#.", "#.#", ".##"),
    "*": ("#.#", ".#.", "#.#", "...", "..."),
    "<": ("..#", ".#.", "#..", ".#.", "..#"),
    ">": ("#..", ".#.", "..#", ".#.", "#.."),
    "|": ("#", "#", "#", "#", "#"),
    "•": ("...", ".#.", ".#.", "...", "..."),
    "·": ("...", "...", ".#.", "...", "..."),
    "▲": ("...", ".#.", "###", "...", "..."),
    "▼": ("...", "###", ".#.", "...", "..."),
}

# 4x6 compact crisp font (great for 5-char tile values & table values)
FONT_4X6: dict[str, tuple[str, ...]] = {
    " ": ("..", "..", "..", "..", "..", ".."),
    "0": (".##.", "#..#", "#.##", "##.#", "#..#", ".##."),
    "1": ("..#.", ".##.", "..#.", "..#.", "..#.", ".###"),
    "2": (".##.", "#..#", "...#", "..#.", ".#..", "####"),
    "3": ("###.", "...#", ".##.", "...#", "...#", "###."),
    "4": ("#..#", "#..#", "####", "...#", "...#", "...#"),
    "5": ("####", "#...", "###.", "...#", "...#", "###."),
    "6": (".##.", "#...", "###.", "#..#", "#..#", ".##."),
    "7": ("####", "...#", "..#.", ".#..", ".#..", ".#.."),
    "8": (".##.", "#..#", ".##.", "#..#", "#..#", ".##."),
    "9": (".##.", "#..#", ".###", "...#", "...#", ".##."),
    "A": (".##.", "#..#", "####", "#..#", "#..#", "#..#"),
    "B": ("###.", "#..#", "###.", "#..#", "#..#", "###."),
    "C": (".###", "#...", "#...", "#...", "#...", ".###"),
    "D": ("###.", "#..#", "#..#", "#..#", "#..#", "###."),
    "E": ("####", "#...", "###.", "#...", "#...", "####"),
    "F": ("####", "#...", "###.", "#...", "#...", "#..."),
    "G": (".###", "#...", "#.##", "#..#", "#..#", ".###"),
    "H": ("#..#", "#..#", "####", "#..#", "#..#", "#..#"),
    "I": ("###", ".#.", ".#.", ".#.", ".#.", "###"),
    "J": ("..##", "...#", "...#", "#..#", "#..#", ".##."),
    "K": ("#..#", "#.#.", "##..", "#.#.", "#..#", "#..#"),
    "L": ("#...", "#...", "#...", "#...", "#...", "####"),
    "M": ("#..#", "####", "####", "#..#", "#..#", "#..#"),
    "N": ("#..#", "##.#", "#.##", "#..#", "#..#", "#..#"),
    "O": (".##.", "#..#", "#..#", "#..#", "#..#", ".##."),
    "P": ("###.", "#..#", "###.", "#...", "#...", "#..."),
    "Q": (".##.", "#..#", "#..#", "#.##", ".###", "...#"),
    "R": ("###.", "#..#", "###.", "#.#.", "#..#", "#..#"),
    "S": (".###", "#...", ".##.", "...#", "...#", "###."),
    "T": ("####", ".#..", ".#..", ".#..", ".#..", ".#.."),
    "U": ("#..#", "#..#", "#..#", "#..#", "#..#", ".##."),
    "V": ("#..#", "#..#", "#..#", "#..#", ".##.", ".##."),
    "W": ("#..#", "#..#", "#..#", "####", "####", "#..#"),
    "X": ("#..#", "#..#", ".##.", ".##.", "#..#", "#..#"),
    "Y": ("#..#", "#..#", ".##.", ".#..", ".#..", ".#.."),
    "Z": ("####", "...#", "..#.", ".#..", "#...", "####"),
    "a": ("....", ".##.", "...#", ".###", "#..#", ".###"),
    "b": ("#...", "#...", "###.", "#..#", "#..#", "###."),
    "c": ("....", ".###", "#...", "#...", "#...", ".###"),
    "d": ("...#", "...#", ".###", "#..#", "#..#", ".###"),
    "e": ("....", ".##.", "#..#", "####", "#...", ".###"),
    "f": ("..##", ".#..", "###.", ".#..", ".#..", ".#.."),
    "g": ("....", ".###", "#..#", ".###", "...#", "###."),
    "h": ("#...", "#...", "###.", "#..#", "#..#", "#..#"),
    "i": (".#.", "...", ".#.", ".#.", ".#.", ".#."),
    "j": ("..#.", "....", "..#.", "..#.", "#.#.", ".#.."),
    "k": ("#...", "#..#", "#.#.", "##..", "#.#.", "#..#"),
    "l": ("#.", "#.", "#.", "#.", "#.", ".#"),
    "m": ("....", "####", "####", "#..#", "#..#", "#..#"),
    "n": ("....", "###.", "#..#", "#..#", "#..#", "#..#"),
    "o": ("....", ".##.", "#..#", "#..#", "#..#", ".##."),
    "p": ("....", "###.", "#..#", "###.", "#...", "#..."),
    "q": ("....", ".###", "#..#", ".###", "...#", "...#"),
    "r": ("....", ".###", "#...", "#...", "#...", "#..."),
    "s": ("....", ".###", "#...", ".##.", "...#", "###."),
    "t": (".#..", "###.", ".#..", ".#..", ".#..", "..##"),
    "u": ("....", "#..#", "#..#", "#..#", "#..#", ".###"),
    "v": ("....", "#..#", "#..#", "#..#", ".##.", ".##."),
    "w": ("....", "#..#", "#..#", "####", "####", "#..#"),
    "x": ("....", "#..#", ".##.", ".##.", "#..#", "#..#"),
    "y": ("....", "#..#", "#..#", ".###", "...#", "###."),
    "z": ("....", "####", "..#.", ".#..", "#...", "####"),
    ".": (".", ".", ".", ".", ".", "#"),
    ",": (".", ".", ".", ".", "#", "#"),
    ":": (".", "#", ".", ".", "#", "."),
    "!": ("#", "#", "#", "#", ".", "#"),
    "?": (".##.", "#..#", "..#.", ".#..", "....", ".#.."),
    "-": ("....", "....", "###.", "....", "....", "...."),
    "—": ("....", "....", "####", "....", "....", "...."),
    "–": ("....", "....", "###.", "....", "....", "...."),
    "+": ("....", ".#..", "###.", ".#..", "....", "...."),
    "/": ("...#", "..#.", "..#.", ".#..", "#...", "#..."),
    "%": ("#..#", "...#", "..#.", ".#..", "#...", "#..#"),
    "$": (".##.", "####", "##..", ".###", "...#", "###."),
    "°": (".##.", "#..#", ".##.", "....", "....", "...."),
    "_": ("....", "....", "....", "....", "....", "####"),
    "(": (".#", "#.", "#.", "#.", "#.", ".#"),
    ")": ("#.", ".#", ".#", ".#", ".#", "#."),
}

# 5x7 crisp geometric medium font (Braun/TE hardware style)
FONT_5X7: dict[str, tuple[str, ...]] = {
    " ": ("...", "...", "...", "...", "...", "...", "..."),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": (".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "####.", "#...#", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."),
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".###.", "#...#", "#....", "#..##", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "J": ("..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".###.", "#...#", "#....", ".###.", "....#", "#...#", ".###."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "a": (".....", ".....", ".###.", "....#", ".####", "#...#", ".####"),
    "b": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "####."),
    "c": (".....", ".....", ".###.", "#...#", "#....", "#...#", ".###."),
    "d": ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    "f": ("..##.", ".#..#", ".#...", "###..", ".#...", ".#...", ".#..."),
    "g": (".....", ".....", ".####", "#...#", ".####", "....#", ".###."),
    "h": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "i": (".#.", "...", "##.", ".#.", ".#.", ".#.", "###"),
    "j": ("..#.", "....", ".##.", "..#.", "..#.", "#.#.", ".#.."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "l": ("##.", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#...#", "#...#"),
    "n": (".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "p": (".....", ".....", "####.", "#...#", "####.", "#....", "#...."),
    "q": (".....", ".....", ".####", "#...#", ".####", "....#", "....#"),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "s": (".....", ".....", ".####", "#....", ".###.", "....#", "####."),
    "t": (".#...", ".#...", "####.", ".#...", ".#...", ".#..#", "..##."),
    "u": (".....", ".....", "#...#", "#...#", "#...#", "#...#", ".####"),
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "w": (".....", ".....", "#...#", "#...#", "#.#.#", "##.##", "#...#"),
    "x": (".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "y": (".....", ".....", "#...#", "#...#", ".####", "....#", ".###."),
    "z": (".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"),
    ".": ("..", "..", "..", "..", "..", "##", "##"),
    ",": ("..", "..", "..", "..", ".#", ".#", "#."),
    ":": ("..", ".#", ".#", "..", ".#", ".#", ".."),
    "!": (".#.", ".#.", ".#.", ".#.", ".#.", "...", ".#."),
    "?": (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    "-": (".....", ".....", ".....", "####.", ".....", ".....", "....."),
    "—": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "–": (".....", ".....", ".....", "####.", ".....", ".....", "....."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "=": (".....", ".....", "#####", ".....", "#####", ".....", "....."),
    "/": ("....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."),
    "%": ("##..#", "##.#.", "..#..", ".#...", "#..##", "#..##", "....."),
    "$": ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    "€": ("..###", ".#...", "####.", ".#...", "####.", ".#...", "..###"),
    "£": ("..##.", ".#..#", ".#...", "####.", ".#...", ".#...", "#####"),
    "°": (".##.", "#..#", ".##.", "....", "....", "....", "...."),
    "'": ("#", "#", ".", ".", ".", ".", "."),
    '"': ("#.#", "#.#", "...", "...", "...", "...", "..."),
    "(": ("..#", ".#.", "#..", "#..", "#..", ".#.", "..#"),
    ")": ("#..", ".#.", "..#", "..#", "..#", ".#.", "#.."),
    "#": (".#.#.", "#####", ".#.#.", ".#.#.", "#####", ".#.#.", "....."),
    "@": (".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    "•": ("...", "...", ".#.", "###", ".#.", "...", "..."),
    "·": ("...", "...", "...", ".#.", "...", "...", "..."),
}

# 7x11 bold geometric hero font (2px strokes, chamfered corners — Braun/TE KPI look)
FONT_7X11: dict[str, tuple[str, ...]] = {
    " ": ("...", "...", "...", "...", "...", "...", "...", "...", "...", "...", "..."),
    "0": (
        ".#####.",
        "#######",
        "##...##",
        "##..###",
        "##.#.##",
        "##.#.##",
        "###..##",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "1": (
        "..###..",
        ".####..",
        "#####..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "...##..",
        "#######",
        "#######",
    ),
    "2": (
        ".#####.",
        "#######",
        "##...##",
        ".....##",
        "....##.",
        "..###..",
        ".###...",
        "##.....",
        "##.....",
        "#######",
        "#######",
    ),
    "3": (
        ".#####.",
        "#######",
        "##...##",
        ".....##",
        "..####.",
        "..####.",
        ".....##",
        ".....##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "4": (
        "...###.",
        "..####.",
        ".##.##.",
        "##..##.",
        "##..##.",
        "#######",
        "#######",
        "....##.",
        "....##.",
        "....##.",
        "....##.",
    ),
    "5": (
        "#######",
        "#######",
        "##.....",
        "##.....",
        "######.",
        ".######",
        ".....##",
        ".....##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "6": (
        ".#####.",
        "#######",
        "##.....",
        "##.....",
        "######.",
        "#######",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "7": (
        "#######",
        "#######",
        ".....##",
        "....##.",
        "....##.",
        "...##..",
        "...##..",
        "..##...",
        "..##...",
        "..##...",
        "..##...",
    ),
    "8": (
        ".#####.",
        "#######",
        "##...##",
        "##...##",
        ".#####.",
        ".#####.",
        "##...##",
        "##...##",
        "##...##",
        "#######",
        ".#####.",
    ),
    "9": (
        ".#####.",
        "#######",
        "##...##",
        "##...##",
        "#######",
        ".######",
        ".....##",
        ".....##",
        "##...##",
        "#######",
        ".#####.",
    ),
    ".": ("..", "..", "..", "..", "..", "..", "..", "..", "..", "##", "##"),
    ",": ("..", "..", "..", "..", "..", "..", "..", "..", ".#", "##", "#."),
    ":": ("..", "..", "##", "##", "..", "..", "..", "##", "##", "..", ".."),
    "-": (".....", ".....", ".....", ".....", "#####", "#####", ".....", ".....", ".....", ".....", "....."),
    "—": (".......", ".......", ".......", ".......", "#######", "#######", ".......", ".......", ".......", ".......", "......."),
    "+": (".....", ".....", "..#..", "..#..", "#####", "#####", "..#..", "..#..", ".....", ".....", "....."),
    "$": (
        "...#...",
        ".#####.",
        "#######",
        "##.#...",
        ".#####.",
        "..#####",
        "...#.##",
        "##.#.##",
        "#######",
        ".#####.",
        "...#...",
    ),
    "%": (
        "##...##",
        "##..##.",
        "....##.",
        "...##..",
        "..##...",
        "..##...",
        ".##....",
        ".##..##",
        "##...##",
        ".......",
        ".......",
    ),
    "°": (
        ".###.",
        "##.##",
        "##.##",
        ".###.",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
    ),
    "K": (
        "##...##",
        "##..##.",
        "##.##..",
        "####...",
        "###....",
        "####...",
        "##.##..",
        "##..##.",
        "##...##",
        "##...##",
        "##...##",
    ),
    "M": (
        "##...##",
        "###.###",
        "#######",
        "##.#.##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
    ),
    "k": (
        "##....",
        "##....",
        "##..##",
        "##.##.",
        "####..",
        "###...",
        "####..",
        "##.##.",
        "##..##",
        "##..##",
        "##..##",
    ),
    "m": (
        ".......",
        ".......",
        ".......",
        "###.##.",
        "#######",
        "##.#.##",
        "##.#.##",
        "##...##",
        "##...##",
        "##...##",
        "##...##",
    ),
    "s": (
        "......",
        "......",
        "......",
        ".#####",
        "##....",
        ".####.",
        "..####",
        "....##",
        "##..##",
        "#####.",
        "......",
    ),
    "d": (
        "....##",
        "....##",
        "....##",
        ".#####",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        ".#####",
        "......",
    ),
    "h": (
        "##....",
        "##....",
        "##....",
        "#####.",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "......",
    ),
}


def _glyph_for(font: dict[str, tuple[str, ...]], ch: str) -> tuple[str, ...]:
    if ch in font:
        return font[ch]
    upper = ch.upper()
    if upper in font:
        return font[upper]
    lower = ch.lower()
    if lower in font:
        return font[lower]
    return font.get("?", font[" "])


def _can_use_font(font: dict[str, tuple[str, ...]], text: str) -> bool:
    for ch in text:
        if ch not in font and ch.upper() not in font and ch.lower() not in font:
            return False
    return True


def measure_text(text: str, font: dict[str, tuple[str, ...]], spacing: int = 1) -> tuple[int, int]:
    """Return (width, height) in pixels for text rendered with a bitmap font."""
    if not text:
        sample = next(iter(font.values()))
        return 0, len(sample)
    width = 0
    height = 0
    for idx, ch in enumerate(text):
        g = _glyph_for(font, ch)
        width += len(g[0])
        if idx < len(text) - 1:
            width += spacing
        height = max(height, len(g))
    return width, height


def draw_text(
    img: Image.Image,
    x: int,
    y: int,
    text: str,
    color: RGB,
    font: dict[str, tuple[str, ...]] = FONT_3X5,
    *,
    spacing: int = 1,
    clip_x: tuple[int, int] | None = None,
) -> int:
    """Draw crisp bitmap pixel text onto img; returns ending x coordinate."""
    if not text:
        return x
    pixels = img.load()
    w, h = img.size
    cx = x
    for ch in text:
        glyph = _glyph_for(font, ch)
        gw = len(glyph[0])
        for ry, row in enumerate(glyph):
            py = y + ry
            if py < 0 or py >= h:
                continue
            for rx, bit in enumerate(row):
                if bit != "#":
                    continue
                px = cx + rx
                if px < 0 or px >= w:
                    continue
                if clip_x is not None and (px < clip_x[0] or px >= clip_x[1]):
                    continue
                pixels[px, py] = color
        cx += gw + spacing
    return cx - spacing


def truncate_text(text: str, max_width: int, font: dict[str, tuple[str, ...]] = FONT_3X5, spacing: int = 1) -> str:
    """Truncate text so it fits within max_width pixels."""
    if measure_text(text, font, spacing)[0] <= max_width:
        return text
    out = text
    while out and measure_text(out, font, spacing)[0] > max_width:
        out = out[:-1]
    return out.rstrip()


def choose_font_for_width(
    text: str,
    max_width: int,
    candidates: tuple[dict[str, tuple[str, ...]], ...] = (FONT_7X11, FONT_5X7, FONT_4X6, FONT_3X5),
    spacing: int = 1,
) -> dict[str, tuple[str, ...]]:
    """Pick the largest candidate font that contains all characters and fits max_width."""
    for font in candidates:
        if font is FONT_7X11 and not _can_use_font(font, text):
            continue
        w, _ = measure_text(text, font, spacing)
        if w <= max_width:
            return font
    return candidates[-1]


# ---------------------------------------------------------------------------
# Hardware-instrument chrome primitives
# ---------------------------------------------------------------------------

def _put(pixels: Any, w: int, h: int, x: int, y: int, color: RGB) -> None:
    if 0 <= x < w and 0 <= y < h:
        pixels[x, y] = color


def _draw_chamfered_box(
    img: Image.Image,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    fill: RGB,
    border: RGB | None = None,
    chamfer: bool = True,
) -> None:
    """Draw a pixel-crisp dark card box with optional 1px chamfered hardware corners."""
    pixels = img.load()
    w, h = img.size
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            is_corner = chamfer and (x in (x0, x1) and y in (y0, y1))
            if is_corner:
                continue
            is_edge = x in (x0, x1) or y in (y0, y1)
            if is_edge and border is not None:
                _put(pixels, w, h, x, y, border)
            else:
                _put(pixels, w, h, x, y, fill)
    # Optional inner diagonal corner pixel when chamfered + bordered
    if chamfer and border is not None and (x1 - x0) >= 3 and (y1 - y0) >= 3:
        for cx, cy in ((x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)):
            _put(pixels, w, h, cx, cy, blend(border, fill, 0.45))


def _draw_status_pip(img: Image.Image, cx: int, cy: int, color: RGB, bg: RGB) -> None:
    """Draw a tiny glowing 2x2 hardware LED status indicator."""
    pixels = img.load()
    w, h = img.size
    halo = blend(color, bg, 0.28)
    core = _brighten(color, 0.35)
    for dy in (-1, 0, 1, 2):
        for dx in (-1, 0, 1, 2):
            if (dx in (-1, 2)) and (dy in (-1, 2)):
                continue
            if 0 <= dx <= 1 and 0 <= dy <= 1:
                _put(pixels, w, h, cx + dx, cy + dy, core if (dx == 0 and dy == 0) else color)
            else:
                _put(pixels, w, h, cx + dx, cy + dy, halo)


def _draw_header(
    img: Image.Image,
    title: str,
    accent: RGB,
    title_color: RGB = DEFAULT_TITLE,
    right_text: str = "",
    right_color: RGB | None = None,
) -> int:
    """Draw the 11px top hardware instrument header bar; returns next usable y."""
    w, _ = img.size
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w - 1, 9], fill=BG_HEADER)
    # Thin bottom hairline + glowing accent segment on the left
    draw.line([0, 10, w - 1, 10], fill=BORDER_SUBTLE)
    draw.line([0, 10, 13, 10], fill=blend(accent, BORDER_SUBTLE, 0.85))
    draw.line([14, 10, 18, 10], fill=blend(accent, BORDER_SUBTLE, 0.35))

    _draw_status_pip(img, 3, 4, accent, BG_HEADER)

    right_w = 0
    if right_text:
        rt = truncate_text(right_text.upper(), 28, FONT_3X5)
        right_w, _ = measure_text(rt, FONT_3X5)
        draw_text(img, w - 3 - right_w, 3, rt, right_color or accent, FONT_3X5)

    max_title_w = w - 10 - (right_w + 4 if right_w else 2)
    clean_title = truncate_text(title.upper(), max(8, max_title_w), FONT_3X5)
    draw_text(img, 8, 3, clean_title, title_color, FONT_3X5)
    return 11


def _delta_palette(delta_text: str, explicit_color: object = None) -> tuple[RGB, RGB, RGB]:
    """Return (text_color, fill_color, border_color) for a delta badge."""
    if isinstance(explicit_color, str) and explicit_color.strip():
        fg = parse_hex_color(explicit_color, DEFAULT_EMERALD)
    else:
        s = delta_text.strip()
        if s.startswith("-") or s.startswith("▼"):
            fg = DEFAULT_CORAL
        elif s.startswith("+") or s.startswith("▲"):
            fg = DEFAULT_EMERALD
        else:
            fg = DEFAULT_ACCENT
    return fg, blend(fg, BG_CARD, 0.16), blend(fg, BG_CARD, 0.42)


def _format_compact_num(val: float) -> str:
    """Format a float compactly for 64x64 min/max sparkline bounds."""
    if not math.isfinite(val):
        return "0"
    av = abs(val)
    if av >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    if av >= 10_000:
        return f"{val / 1_000:.0f}k"
    if av >= 1_000:
        return f"{val / 1_000:.1f}k"
    if av >= 100 or float(val).is_integer():
        return f"{int(round(val))}"
    return f"{val:.1f}"


# ---------------------------------------------------------------------------
# Layout 1: big_number
# ---------------------------------------------------------------------------

def _render_big_number(data: dict[str, Any], width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BG_CANVAS)
    title = str(data.get("title") or "").strip()
    value = str(data.get("value", "—"))
    unit = str(data.get("unit") or "")
    subtitle = str(data.get("subtitle") or "").strip()
    delta = str(data.get("delta") or "").strip()
    raw_progress = data.get("progress")

    progress: float | None = None
    if raw_progress is not None and raw_progress != "" and not isinstance(raw_progress, bool):
        try:
            p = float(raw_progress)
            if math.isfinite(p):
                progress = p * 100.0 if 0.0 < p <= 1.0 else p
                progress = max(0.0, min(100.0, progress))
        except (TypeError, ValueError):
            progress = None

    primary = parse_hex_color(data.get("color"), DEFAULT_TEXT)
    accent = parse_hex_color(data.get("accent_color"), primary if primary != DEFAULT_TEXT else DEFAULT_ACCENT)
    title_color = parse_hex_color(data.get("title_color"), DEFAULT_TITLE)
    label_color = parse_hex_color(data.get("label_color"), DEFAULT_LABEL)

    top_y = _draw_header(img, title, accent, title_color) if title else 0

    # Inner recessed card frame
    card_y0 = top_y + 2 if title else 2
    card_y1 = height - 3
    _draw_chamfered_box(img, 2, card_y0, width - 3, card_y1, BG_CARD, BORDER_DIM)

    inner_w = width - 10
    card_h = card_y1 - card_y0 + 1

    # Measure value + unit combo with auto-fitting font
    has_separate_unit = bool(unit) and len(unit) <= 3
    unit_font = FONT_5X7
    val_font = choose_font_for_width(value, inner_w - (measure_text(unit, unit_font)[0] + 2 if has_separate_unit else 0))

    if has_separate_unit and val_font is FONT_7X11:
        val_w, val_h = measure_text(value, val_font)
        unit_w, unit_h = measure_text(unit, unit_font)
        total_w = val_w + 1 + unit_w
        if total_w > inner_w:
            has_separate_unit = False
    if not has_separate_unit:
        combined = value + unit
        val_font = choose_font_for_width(combined, inner_w)
        val_w, val_h = measure_text(combined, val_font)
        total_w = val_w
        unit_w, unit_h = 0, 0

    # Compute vertical composition based on optional secondary elements
    has_delta = bool(delta)
    has_sub = bool(subtitle)
    has_prog = progress is not None

    # Stack heights: value block + optional delta pill (9px) + optional subtitle (5px) + optional progress (5px)
    block_h = val_h
    if has_delta:
        block_h += 4 + 9
    if has_sub and not (has_delta and has_prog):
        block_h += 4 + 5
    if has_prog:
        block_h += 5 + 4

    start_y = card_y0 + max(3, (card_h - block_h) // 2)
    cur_y = start_y

    # Subtle radial-like soft accent glow band behind hero metric
    vx = (width - total_w) // 2
    if has_separate_unit and val_font is FONT_7X11:
        draw_text(img, vx, cur_y, value, primary, val_font)
        unit_color = blend(accent, primary, 0.55)
        draw_text(img, vx + val_w + 1, cur_y + val_h - unit_h, unit, unit_color, unit_font)
    else:
        draw_text(img, vx, cur_y, value + unit, primary, val_font)

    cur_y += val_h

    # Optional delta pill (+12.4% emerald / -2.1% coral)
    if has_delta:
        cur_y += 4
        dfg, dbg, dborder = _delta_palette(delta, data.get("delta_color"))
        dtext = truncate_text(delta.upper(), inner_w - 6, FONT_3X5)
        dw, _ = measure_text(dtext, FONT_3X5)
        pill_w = dw + 6
        px0 = (width - pill_w) // 2
        px1 = px0 + pill_w - 1
        _draw_chamfered_box(img, px0, cur_y, px1, cur_y + 8, dbg, dborder)
        draw_text(img, px0 + 3, cur_y + 2, dtext, dfg, FONT_3X5)
        cur_y += 9

    # Optional subtitle (skipped only if both delta AND progress are present to avoid crowding)
    if has_sub and not (has_delta and has_prog):
        cur_y += 4
        sub_text = truncate_text(subtitle.upper(), inner_w, FONT_3X5)
        sw, _ = measure_text(sub_text, FONT_3X5)
        draw_text(img, (width - sw) // 2, cur_y, sub_text, label_color, FONT_3X5)
        cur_y += 5

    # Optional progress bar OR subtle decorative instrument rule
    if has_prog and progress is not None:
        bar_y = min(card_y1 - 6, cur_y + 5)
        bx0, bx1 = 6, width - 7
        bar_w = bx1 - bx0 + 1
        draw = ImageDraw.Draw(img)
        draw.rectangle([bx0, bar_y, bx1, bar_y + 3], fill=(18, 26, 42))
        fill_w = int(round((progress / 100.0) * bar_w))
        if fill_w > 0:
            fx1 = bx0 + fill_w - 1
            draw.rectangle([bx0, bar_y, fx1, bar_y + 3], fill=accent)
            # Crisp bright leading edge
            draw.line([fx1, bar_y, fx1, bar_y + 3], fill=_brighten(accent, 0.55))
    elif not has_delta and not has_sub:
        rule_y = min(card_y1 - 5, cur_y + 6)
        draw = ImageDraw.Draw(img)
        draw.line([16, rule_y, width - 17, rule_y], fill=blend(accent, BG_CARD, 0.30))
        draw.line([26, rule_y, width - 27, rule_y], fill=accent)

    return img


# ---------------------------------------------------------------------------
# Layout 2: sparkline
# ---------------------------------------------------------------------------

def _render_sparkline(data: dict[str, Any], width: int, height: int) -> Image.Image:
    points_raw = data.get("points") or []
    points: list[float] = []
    for p in points_raw:
        try:
            f = float(p)
            if math.isfinite(f):
                points.append(f)
        except (TypeError, ValueError):
            pass

    if not points:
        return _render_error("No data points", width, height)

    img = Image.new("RGB", (width, height), BG_CANVAS)
    title = str(data.get("title") or "").strip()
    value = str(data.get("value") if data.get("value") is not None else _format_compact_num(points[-1]))
    unit = str(data.get("unit") or "")
    if unit and not value.endswith(unit):
        display_value = f"{value}{unit}"
    else:
        display_value = value

    delta = str(data.get("delta") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    fill_area = bool(data.get("fill", True))
    show_minmax = bool(data.get("show_minmax", True))

    accent = parse_hex_color(data.get("color"), DEFAULT_CYAN)
    neg_color = DEFAULT_CORAL
    title_color = parse_hex_color(data.get("title_color"), DEFAULT_TITLE)
    val_color = parse_hex_color(data.get("value_color"), DEFAULT_TEXT)

    # Header bar (title left, optional delta right)
    if title or delta:
        delta_fg = _delta_palette(delta, data.get("delta_color"))[0] if delta else None
        top_y = _draw_header(img, title or "METRIC", accent, title_color, right_text=delta, right_color=delta_fg)
    else:
        top_y = 0

    # Current value readout row
    val_y = top_y + 2
    val_font = choose_font_for_width(display_value, width - 8, (FONT_5X7, FONT_4X6, FONT_3X5))
    vw, vh = measure_text(display_value, val_font)
    draw_text(img, 3, val_y, display_value, val_color, val_font)

    if subtitle:
        sub_max = max(0, width - 6 - vw - 4)
        if sub_max >= 8:
            st = truncate_text(subtitle.upper(), sub_max, FONT_3X5)
            sw, _ = measure_text(st, FONT_3X5)
            draw_text(img, width - 3 - sw, val_y + max(0, vh - 5), st, DEFAULT_MUTED, FONT_3X5)

    # Plot frame coordinates
    px0, px1 = 2, width - 3
    py0 = val_y + vh + 2
    py1 = height - (9 if show_minmax else 3)

    _draw_chamfered_box(img, px0, py0, px1, py1, BG_CARD, BORDER_DIM)

    inner_x0 = px0 + 2
    inner_x1 = px1 - 2
    inner_y0 = py0 + 3
    inner_y1 = py1 - 2
    inner_w = max(1, inner_x1 - inner_x0)
    inner_h = max(4, inner_y1 - inner_y0)

    # Subtle horizontal dashed midline & top guide ticks
    pixels = img.load()
    mid_y = (inner_y0 + inner_y1) // 2
    for gx in range(inner_x0, inner_x1 + 1):
        if (gx - inner_x0) % 4 < 2:
            _put(pixels, width, height, gx, mid_y, GRID_LINE)
        if (gx - inner_x0) % 6 == 0:
            _put(pixels, width, height, gx, inner_y0, GRID_LINE)
    for gx in range(inner_x0, inner_x1 + 1):
        _put(pixels, width, height, gx, inner_y1, BORDER_SUBTLE)

    # Normalize points into pixel coordinates
    y_min = min(points)
    y_max = max(points)
    has_neg = y_min < 0
    if abs(y_max - y_min) < 1e-9:
        lo = y_min - 1.0
        hi = y_max + 1.0
    else:
        pad = (y_max - y_min) * 0.12
        lo = (y_min - pad) if has_neg else max(0.0, y_min - pad)
        hi = y_max + pad

    def map_y(val: float) -> float:
        t = (val - lo) / (hi - lo)
        return inner_y1 - t * inner_h

    n = len(points)
    coords: list[tuple[float, float, float]] = []
    for i, v in enumerate(points):
        fx = inner_x0 + (inner_w * i / (n - 1)) if n > 1 else (inner_x0 + inner_x1) / 2.0
        fy = map_y(v)
        coords.append((fx, fy, v))

    # Build per-column curve height via piecewise linear interpolation
    col_y: dict[int, tuple[float, float]] = {}
    if len(coords) == 1:
        cx_i = int(round(coords[0][0]))
        col_y[cx_i] = (coords[0][1], coords[0][2])
    else:
        for i in range(len(coords) - 1):
            x_a, y_a, v_a = coords[i]
            x_b, y_b, v_b = coords[i + 1]
            ix_start = max(inner_x0, int(math.floor(x_a)))
            ix_end = min(inner_x1, int(math.ceil(x_b)))
            span = max(1e-6, x_b - x_a)
            for ix in range(ix_start, ix_end + 1):
                t = max(0.0, min(1.0, (ix - x_a) / span))
                col_y[ix] = (y_a + (y_b - y_a) * t, v_a + (v_b - v_a) * t)

    # Shaded vertical phosphor gradient fill under the curve
    if fill_area:
        for ix, (fy, fv) in col_y.items():
            seg_color = neg_color if fv < 0 else accent
            top_px = int(math.ceil(fy))
            for iy in range(max(inner_y0, top_px), inner_y1 + 1):
                depth = (iy - fy) / max(1.0, (inner_y1 - fy))
                alpha = max(0.04, 0.42 * (1.0 - depth) ** 1.25)
                base_bg = pixels[ix, iy]
                pixels[ix, iy] = blend(seg_color, base_bg, alpha)

    # Crisp 1px curve with soft LED luminescence underneath
    for i in range(len(coords) - 1):
        x_a, y_a, v_a = coords[i]
        x_b, y_b, v_b = coords[i + 1]
        steps = max(1, int(math.ceil(max(abs(x_b - x_a), abs(y_b - y_a)) * 2)))
        seg_color = neg_color if (v_a < 0 and v_b < 0) else accent
        glow_color = blend(seg_color, BG_CARD, 0.45)
        for s in range(steps + 1):
            t = s / steps
            px = int(round(x_a + (x_b - x_a) * t))
            py = int(round(y_a + (y_b - y_a) * t))
            if inner_x0 <= px <= inner_x1 and inner_y0 <= py <= inner_y1:
                if py + 1 <= inner_y1:
                    pixels[px, py + 1] = blend(glow_color, pixels[px, py + 1], 0.5)
                pixels[px, py] = seg_color

    # Glowing latest-point beacon
    lx, ly, lv = coords[-1]
    lxi, lyi = int(round(lx)), int(round(ly))
    dot_color = neg_color if lv < 0 else accent
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            dist = abs(dx) + abs(dy)
            if dist > 2:
                continue
            tx, ty = lxi + dx, lyi + dy
            if inner_x0 - 1 <= tx <= inner_x1 + 1 and inner_y0 - 1 <= ty <= inner_y1 + 1:
                if dist == 0:
                    pixels[tx, ty] = (255, 255, 255)
                elif dist == 1:
                    pixels[tx, ty] = _brighten(dot_color, 0.25)
                else:
                    pixels[tx, ty] = blend(dot_color, pixels[tx, ty], 0.30)

    # Subtle min / max footer
    if show_minmax:
        lo_str = _format_compact_num(y_min)
        hi_str = _format_compact_num(y_max)
        lo_label = f"L {lo_str}"
        hi_label = f"H {hi_str}"
        lw, _ = measure_text(lo_label, FONT_3X5)
        hw, _ = measure_text(hi_label, FONT_3X5)
        if lw + hw + 8 > width:
            lo_label = lo_str
            hi_label = hi_str
            hw, _ = measure_text(hi_label, FONT_3X5)
        fy_txt = height - 6
        draw_text(img, 3, fy_txt, lo_label, DEFAULT_MUTED, FONT_3X5)
        draw_text(img, width - 3 - hw, fy_txt, hi_label, DEFAULT_LABEL, FONT_3X5)

    return img


# ---------------------------------------------------------------------------
# Layout 3: multi_stat
# ---------------------------------------------------------------------------

_TILE_ACCENTS: tuple[RGB, ...] = (
    (91, 206, 250),   # cyan
    (255, 158, 61),   # amber/flame
    (46, 229, 141),   # emerald
    (186, 138, 255),  # violet
)


def _render_multi_stat(data: dict[str, Any], width: int, height: int) -> Image.Image:
    stats = list(data.get("stats") or [])[:4]
    if not stats:
        return _render_error("No stats", width, height)

    img = Image.new("RGB", (width, height), BG_CANVAS)
    title = str(data.get("title") or "").strip()
    title_color = parse_hex_color(data.get("title_color"), DEFAULT_TITLE)
    label_color = parse_hex_color(data.get("label_color"), DEFAULT_LABEL)
    default_val_color = parse_hex_color(data.get("value_color"), DEFAULT_TEXT)

    first_accent = parse_hex_color(stats[0].get("color"), DEFAULT_ACCENT) if stats else DEFAULT_ACCENT
    header_accent = parse_hex_color(data.get("accent_color"), first_accent)
    top_y = _draw_header(img, title, header_accent, title_color) if title else 0

    body_y0 = top_y + 2 if title else 2
    body_y1 = height - 2
    body_h = body_y1 - body_y0 + 1

    n = len(stats)
    draw = ImageDraw.Draw(img)

    def draw_tile(x0: int, y0: int, x1: int, y1: int, stat: dict[str, Any], idx: int, tall: bool) -> None:
        tw = x1 - x0 + 1
        th = y1 - y0 + 1
        raw_c = stat.get("color")
        val_color = parse_hex_color(raw_c, default_val_color) if raw_c else default_val_color
        # If stat color is plain white, give the top accent stripe a tasteful instrument color
        if raw_c and parse_hex_color(raw_c, DEFAULT_TEXT) != (255, 255, 255):
            stripe = val_color
        else:
            stripe = _TILE_ACCENTS[idx % len(_TILE_ACCENTS)]

        _draw_chamfered_box(img, x0, y0, x1, y1, BG_CARD, BORDER_DIM)

        # Crisp colored top accent bar + subtle 1px tinted glow
        draw.line([x0 + 2, y0 + 1, x1 - 2, y0 + 1], fill=stripe)
        draw.line([x0 + 2, y0 + 2, x1 - 2, y0 + 2], fill=blend(stripe, BG_CARD, 0.20))

        inner_w = tw - 4
        label = str(stat.get("label") or "").strip()
        value = str(stat.get("value", "—")).strip()

        if tall:
            # 1x1 or 2x1 tall tile
            val_font = choose_font_for_width(value, inner_w, (FONT_7X11, FONT_5X7, FONT_4X6, FONT_3X5))
            vw, vh = measure_text(value, val_font)
            lbl = truncate_text(label.upper(), inner_w, FONT_3X5)
            lw, lh = measure_text(lbl, FONT_3X5)
            gap = 5
            content_h = lh + gap + vh
            sy = y0 + 3 + max(2, (th - 5 - content_h) // 2)
            draw_text(img, x0 + (tw - lw) // 2, sy, lbl, label_color, FONT_3X5)
            draw_text(img, x0 + (tw - vw) // 2, sy + lh + gap, value, val_color, val_font)
        else:
            # 2x2 compact hardware tile (29x24)
            lbl = truncate_text(label.upper(), inner_w, FONT_3X5)
            draw_text(img, x0 + 3, y0 + 4, lbl, label_color, FONT_3X5)

            val_font = choose_font_for_width(value, inner_w - 1, (FONT_5X7, FONT_4X6, FONT_3X5))
            vw, vh = measure_text(value, val_font)
            val_y = y0 + 11 + max(0, (th - 13 - vh) // 2)
            draw_text(img, x0 + 3, val_y, value, val_color, val_font)

    if n == 1:
        draw_tile(2, body_y0, width - 3, body_y1, stats[0], 0, tall=True)
    elif n == 2:
        mid = width // 2
        draw_tile(2, body_y0, mid - 2, body_y1, stats[0], 0, tall=True)
        draw_tile(mid + 1, body_y0, width - 3, body_y1, stats[1], 1, tall=True)
    else:
        mid_x = width // 2
        row_h = (body_h - 2) // 2
        r0_y0 = body_y0
        r0_y1 = r0_y0 + row_h - 1
        r1_y0 = r0_y1 + 2
        r1_y1 = min(body_y1, r1_y0 + row_h - 1)
        boxes = [
            (2, r0_y0, mid_x - 2, r0_y1),
            (mid_x + 1, r0_y0, width - 3, r0_y1),
            (2, r1_y0, mid_x - 2, r1_y1),
            (mid_x + 1, r1_y0, width - 3, r1_y1),
        ]
        # If exactly 3 stats, let the 3rd tile span full width cleanly!
        if n == 3:
            boxes[2] = (2, r1_y0, width - 3, r1_y1)
        for idx, stat in enumerate(stats[:n]):
            x0, y0, x1, y1 = boxes[idx]
            draw_tile(x0, y0, x1, y1, stat, idx, tall=False)

    return img


# ---------------------------------------------------------------------------
# Layout 4: key_value
# ---------------------------------------------------------------------------

def _render_key_value(data: dict[str, Any], width: int, height: int) -> Image.Image:
    items = list(data.get("items") or [])[:5]
    if not items:
        return _render_error("No items", width, height)

    img = Image.new("RGB", (width, height), BG_CANVAS)
    title = str(data.get("title") or "").strip()
    key_color = parse_hex_color(data.get("key_color"), DEFAULT_LABEL)
    val_color = parse_hex_color(data.get("value_color"), DEFAULT_TEXT)
    title_color = parse_hex_color(data.get("title_color"), DEFAULT_TITLE)
    accent = parse_hex_color(data.get("accent_color"), parse_hex_color(data.get("color"), DEFAULT_CYAN))

    top_y = _draw_header(img, title, accent, title_color) if title else 0
    body_y0 = top_y + 2 if title else 2
    body_y1 = height - 2
    avail_h = body_y1 - body_y0 + 1

    n = len(items)
    row_step = min(12, max(9, avail_h // n))
    band_h = row_step - 1
    total_h = n * row_step - 1
    start_y = body_y0 + max(0, (avail_h - total_h) // 2)

    draw = ImageDraw.Draw(img)
    for idx, item in enumerate(items):
        ry0 = start_y + idx * row_step
        ry1 = min(body_y1, ry0 + band_h - 1)
        band_bg = BG_CARD if idx % 2 == 0 else BG_CARD_ALT
        draw.rectangle([2, ry0, width - 3, ry1], fill=band_bg)
        # Subtle 2x2 status pip on the left
        row_accent = parse_hex_color(item.get("color"), _TILE_ACCENTS[idx % len(_TILE_ACCENTS)])
        pip_y = ry0 + max(1, (band_h - 2) // 2)
        draw.rectangle([3, pip_y, 4, pip_y + 1], fill=row_accent)

        key_raw = str(item.get("key", "")).strip()
        val_raw = str(item.get("value", "")).strip()
        row_val_color = parse_hex_color(item.get("color"), val_color) if item.get("color") else val_color

        # Choose value font (4x6 on taller rows if room permits, else crisp 3x5)
        val_font = FONT_4X6 if band_h >= 10 else FONT_3X5
        vw, vh = measure_text(val_raw, val_font)
        if vw > 28:
            val_font = FONT_3X5
            vw, vh = measure_text(val_raw, val_font)
        val_text = truncate_text(val_raw, 34, val_font)
        vw, vh = measure_text(val_text, val_font)

        key_max_w = max(8, (width - 3 - vw) - 10)
        key_text = truncate_text(key_raw.upper(), key_max_w, FONT_3X5)

        key_y = ry0 + max(1, (band_h - 5) // 2)
        val_y = ry0 + max(1, (band_h - vh) // 2)

        draw_text(img, 7, key_y, key_text, key_color, FONT_3X5)
        draw_text(img, width - 3 - vw, val_y, val_text, row_val_color, val_font)

    return img


# ---------------------------------------------------------------------------
# Layout 5: marquee
# ---------------------------------------------------------------------------

def _render_marquee_frames(data: dict[str, Any], width: int, height: int) -> tuple[list[Image.Image], list[int]]:
    text = str(data.get("text") or "").strip() or "—"
    title = str(data.get("title") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    color = parse_hex_color(data.get("color"), DEFAULT_TEXT)
    title_color = parse_hex_color(data.get("title_color"), DEFAULT_TITLE)
    accent = parse_hex_color(data.get("accent_color"), color if color != DEFAULT_TEXT else DEFAULT_ACCENT)

    # Build static base frame
    base = Image.new("RGB", (width, height), BG_CANVAS)
    draw = ImageDraw.Draw(base)
    if title:
        top_y = _draw_header(base, title, accent, title_color)
        track_y0 = top_y + 7
        track_y1 = height - 16
    else:
        # Minimal notification chrome
        draw.line([4, 4, width - 5, 4], fill=BORDER_SUBTLE)
        draw.line([4, 4, 18, 4], fill=accent)
        track_y0 = 14
        track_y1 = height - 15

    # Recessed LED ticker tape housing
    _draw_chamfered_box(base, 2, track_y0, width - 3, track_y1, BG_CARD, BORDER_SUBTLE)
    draw.line([4, track_y0 + 1, width - 5, track_y0 + 1], fill=blend(accent, BG_CARD, 0.45))
    draw.line([4, track_y1 - 1, width - 5, track_y1 - 1], fill=blend(accent, BG_CARD, 0.25))

    # Footer instrument ticks or subtitle
    if subtitle:
        st = truncate_text(subtitle.upper(), width - 10, FONT_3X5)
        sw, _ = measure_text(st, FONT_3X5)
        draw_text(base, (width - sw) // 2, height - 9, st, DEFAULT_MUTED, FONT_3X5)
    else:
        tick_y = height - 7
        for tx in range(4, width - 4, 4):
            tick_h = 2 if (tx - 4) % 16 == 0 else 1
            col = blend(accent, BORDER_SUBTLE, 0.5) if tick_h == 2 else BORDER_SUBTLE
            draw.line([tx, tick_y, tx, tick_y + tick_h], fill=col)

    clip_x0 = 4
    clip_x1 = width - 4
    track_w = clip_x1 - clip_x0
    font = FONT_5X7
    tw, th = measure_text(text, font)
    text_y = track_y0 + (track_y1 - track_y0 + 1 - th) // 2

    if tw <= track_w:
        # Fits cleanly without scrolling — return single crisp static frame
        draw_text(base, clip_x0 + (track_w - tw) // 2, text_y, text, color, font, clip_x=(clip_x0, clip_x1))
        return [base], [1000]

    # Smooth horizontal scrolling ticker with brief leading pause
    spacer = 18
    loop_len = tw + spacer
    step = 1 if loop_len <= 160 else 2
    offsets = [0] + list(range(0, loop_len, step))
    frames: list[Image.Image] = []
    durations: list[int] = []

    for i, off in enumerate(offsets):
        frame = base.copy()
        draw_text(frame, clip_x0 - off, text_y, text, color, font, clip_x=(clip_x0, clip_x1))
        if clip_x0 - off + loop_len < clip_x1:
            draw_text(frame, clip_x0 - off + loop_len, text_y, text, color, font, clip_x=(clip_x0, clip_x1))
        # Subtle 2px edge fade inside ticker aperture
        px = frame.load()
        for fy in range(text_y, text_y + th):
            px[clip_x0, fy] = blend(px[clip_x0, fy], BG_CARD, 0.40)
            px[clip_x1 - 1, fy] = blend(px[clip_x1 - 1, fy], BG_CARD, 0.40)
        frames.append(frame)
        durations.append(700 if i == 0 else 40)

    return frames, durations


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------

def _render_error(msg: str, width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BG_CANVAS)
    _draw_header(img, "PANEL", DEFAULT_CORAL, DEFAULT_TITLE)
    _draw_chamfered_box(img, 3, 15, width - 4, height - 4, (24, 10, 14), (110, 32, 34))
    text = truncate_text(msg.upper(), width - 12, FONT_3X5)
    tw, th = measure_text(text, FONT_3X5)
    draw_text(img, (width - tw) // 2, 15 + (height - 19 - th) // 2, text, DEFAULT_CORAL, FONT_3X5)
    return img


# ---------------------------------------------------------------------------
# Public rendering entry points
# ---------------------------------------------------------------------------

def render_panel_frames(
    data: dict[str, Any],
    width: int = 64,
    height: int = 64,
) -> tuple[list[Image.Image], list[int]]:
    """Render panel JSON data to one or more PIL RGB frames + frame durations (ms)."""
    layout = str(data.get("layout") or "big_number")
    if layout == "big_number":
        return [_render_big_number(data, width, height)], [1000]
    if layout == "sparkline":
        return [_render_sparkline(data, width, height)], [1000]
    if layout == "multi_stat":
        return [_render_multi_stat(data, width, height)], [1000]
    if layout == "key_value":
        return [_render_key_value(data, width, height)], [1000]
    if layout == "marquee":
        return _render_marquee_frames(data, width, height)
    if layout == "_error":
        return [_render_error(str(data.get("message") or "No data"), width, height)], [1000]
    return [_render_error(f"Unknown: {layout}", width, height)], [1000]


def render_panel_to_files(
    data: dict[str, Any],
    output: Path | None,
    output_large: Path | None = None,
    *,
    width: int = 64,
    height: int = 64,
    magnification: int = 10,
) -> None:
    """Render panel JSON directly to native 64x64 and/or magnified WebP files."""
    frames, durations = render_panel_frames(data, width=width, height=height)
    is_animated = len(frames) > 1

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if is_animated:
            frames[0].save(
                output,
                "WEBP",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=0,
                lossless=True,
            )
        else:
            frames[0].save(output, "WEBP", lossless=True)

    if output_large is not None:
        output_large.parent.mkdir(parents=True, exist_ok=True)
        mag = max(1, int(magnification))
        target_size = (width * mag, height * mag)
        large_frames = [f.resize(target_size, Image.Resampling.NEAREST) for f in frames]
        if is_animated:
            large_frames[0].save(
                output_large,
                "WEBP",
                save_all=True,
                append_images=large_frames[1:],
                duration=durations,
                loop=0,
                lossless=True,
            )
        else:
            large_frames[0].save(output_large, "WEBP", lossless=True)
