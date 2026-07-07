"""Render a Track into a 64x64 now-playing card (raw RGB bytes for a FrameSink).

Album art fills the panel dimmed; a scrim darkens the lower third; the title •
artist scrolls if it doesn't fit; a Spotify-green progress bar tracks position.
Cheap enough to redraw every frame so the bar and scroll move smoothly.
"""

from PIL import Image, ImageDraw, ImageFont

from phoenix.nowplaying.source import Track

SIZE = 64
GREEN = (29, 185, 84)
_SCROLL_PX_PER_S = 16.0
_GAP = 14  # px between wrapped copies of the scrolling text


def _cover(img: Image.Image, s: int) -> Image.Image:
    """Center-crop to square, resize to s×s (cover fit)."""
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    return img.crop((left, top, left + side, top + side)).resize((s, s), Image.Resampling.LANCZOS)


class NowPlayingRenderer:
    def __init__(self, size: int = SIZE):
        self.size = size
        self._font = ImageFont.load_default()
        self._scroll = 0.0
        self._key: str | None = None
        # Precompute a bottom scrim (dark gradient) once.
        s = size
        scrim = Image.new("L", (1, s), 0)
        for y in range(s):
            t = max(0.0, (y - s * 0.5) / (s * 0.5))
            scrim.putpixel((0, y), int(215 * t))
        self._scrim = scrim.resize((s, s))
        self._black = Image.new("RGB", (s, s), (0, 0, 0))

    def render(self, track: Track, dt: float) -> bytes:
        s = self.size
        img = Image.new("RGB", (s, s), (14, 8, 16))
        if track.art is not None:
            img.paste(_cover(track.art, s).point(lambda p: int(p * 0.42)), (0, 0))
        img = Image.composite(self._black, img, self._scrim)  # darken lower third
        draw = ImageDraw.Draw(img)

        text = track.title + (f"   •   {track.artist}" if track.artist else "")
        tw = int(draw.textlength(text, font=self._font))
        ty = s - 18
        if track.key != self._key:  # new track → reset scroll
            self._key = track.key
            self._scroll = 0.0
        if tw <= s - 4:
            draw.text(((s - tw) // 2, ty), text, font=self._font, fill=(255, 255, 255))
        else:
            self._scroll += dt * _SCROLL_PX_PER_S
            period = tw + _GAP
            off = self._scroll % period
            for x0 in (4 - off, 4 - off + period):
                draw.text((x0, ty), text, font=self._font, fill=(255, 255, 255))

        # progress bar
        by = s - 3
        draw.rectangle([2, by, s - 3, by + 1], fill=(48, 48, 48))
        fill_w = int((s - 5) * track.progress())
        if fill_w > 0:
            draw.rectangle([2, by, 2 + fill_w, by + 1], fill=GREEN)

        return img.tobytes()

    def render_idle(self) -> bytes:
        """A calm 'nothing playing' frame."""
        s = self.size
        img = Image.new("RGB", (s, s), (14, 8, 16))
        draw = ImageDraw.Draw(img)
        msg = "no music"
        w = int(draw.textlength(msg, font=self._font))
        draw.text(((s - w) // 2, s // 2 - 5), msg, font=self._font, fill=(120, 70, 60))
        return img.tobytes()
