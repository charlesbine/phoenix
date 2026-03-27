"""Spotify Now Playing — pulls from Home Assistant media_player entity.

Two alternating frames:
1. Full-screen album art (64x64)
2. Song info: artist, title, progress bar, small album art
"""

import io
import json
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from phoenix.cache import cache_get
from phoenix.paths import DATA_DIR, ensure_dirs
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

# Try multiple media player entities — Spotify direct + Sonos speakers
MEDIA_PLAYER_ENTITIES = [
    "media_player.spotify_charlesbine",
    "media_player.unnamed_room",
    "media_player.living_room",
    "media_player.bedroom",
    "media_player.bathroom",
    "media_player.kitchen",
]


def _fetch_entity(entity_id: str, settings: Settings) -> dict:
    url = f"{settings.ha_url.rstrip('/')}/api/states/{entity_id}"
    headers = {"Authorization": f"Bearer {settings.ha_token}"}
    try:
        status, body, _ = cache_get(url, ttl=15, headers=headers)
        if status == 200:
            return json.loads(body)
    except Exception:
        pass
    return {}


def _find_playing(settings: Settings) -> dict | None:
    """Find the first media player that's currently playing."""
    for entity_id in MEDIA_PLAYER_ENTITIES:
        data = _fetch_entity(entity_id, settings)
        if data.get("state") == "playing":
            return data
    return None


def _download_art(url: str, settings: Settings) -> Image.Image | None:
    """Download album art from HA's proxied URL."""
    if not url:
        return None
    # HA entity_picture is a relative URL like /api/media_player_proxy/...
    if url.startswith("/"):
        url = f"{settings.ha_url.rstrip('/')}{url}"
    try:
        headers = {"Authorization": f"Bearer {settings.ha_token}"}
        status, body, _ = cache_get(url, ttl=60, headers=headers)
        if status == 200 and body:
            return Image.open(io.BytesIO(body)).convert("RGBA")
    except Exception:
        logger.warning("[spotify] Failed to download album art")
    return None


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    ensure_dirs()

    player = _find_playing(settings)
    if player is None:
        # Not playing — remove outputs so display skips this app
        for f in [output, output_large]:
            if f.exists():
                f.unlink()
        return

    attrs = player.get("attributes", {})
    title = attrs.get("media_title", "Unknown")
    artist = attrs.get("media_artist", "Unknown")
    album = attrs.get("media_album_name", "")
    art_url = attrs.get("entity_picture", "")
    duration = attrs.get("media_duration", 0)
    position = attrs.get("media_position", 0)
    position_updated = attrs.get("media_position_updated_at", "")

    # Extrapolate current position based on when HA last updated it
    if position_updated and duration > 0:
        try:
            from datetime import datetime, timezone
            updated_at = datetime.fromisoformat(position_updated)
            now = datetime.now(timezone.utc)
            elapsed_since_update = (now - updated_at).total_seconds()
            position = min(position + elapsed_since_update, duration)
        except Exception:
            pass

    progress_pct = position / duration if duration > 0 else 0

    # Download album art
    art = _download_art(art_url, settings)

    # Frame 1: Full-screen album art
    frame_art = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    if art:
        resized = art.resize((64, 64), Image.Resampling.LANCZOS)
        frame_art.paste(resized, (0, 0))

    # Frame 2: Song info — small album art + title + artist + progress bar
    # Rendered purely in Pillow (no pixlet dependency)
    frame_info = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    draw = ImageDraw.Draw(frame_info)

    # Small album art in top-left
    if art:
        art_small = art.resize((24, 24), Image.Resampling.LANCZOS)
        frame_info.paste(art_small, (2, 2))

    # Load a bitmap font — Pillow's default is fine for pixel displays
    from PIL import ImageFont
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 7)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 6)
    except OSError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Title (right of album art, wraps below if needed)
    title_x = 29
    title_short = title[:12] if len(title) > 12 else title
    draw.text((title_x, 3), title_short, fill=(255, 255, 255), font=font_large)

    # Artist
    artist_short = artist[:14] if len(artist) > 14 else artist
    draw.text((title_x, 14), artist_short, fill=(179, 179, 179), font=font_small)

    # Time stamps
    position_str = _format_time(position)
    duration_str = _format_time(duration)
    draw.text((2, 30), position_str, fill=(29, 185, 84), font=font_small)
    draw.text((44, 30), duration_str, fill=(100, 100, 100), font=font_small)

    # Progress bar
    bar_y = 40
    bar_h = 3
    draw.rectangle([2, bar_y, 61, bar_y + bar_h - 1], fill=(40, 40, 40))
    bar_width = int(59 * progress_pct)
    if bar_width > 0:
        draw.rectangle([2, bar_y, 2 + bar_width, bar_y + bar_h - 1], fill=(29, 185, 84))

    # Spotify green dot at progress position
    dot_x = 2 + bar_width
    draw.ellipse([dot_x - 1, bar_y - 1, dot_x + 2, bar_y + bar_h], fill=(29, 185, 84))

    # Save as animated webp — 5 seconds per frame
    frames = [frame_art, frame_info]
    frame_duration = 5000

    frames[0].save(
        output, "WEBP", save_all=True, append_images=frames[1:],
        duration=[frame_duration] * len(frames), loop=0,
    )

    # Magnified version
    mag = settings.magnification
    large_frames = [
        f.resize((64 * mag, 64 * mag), Image.Resampling.NEAREST)
        for f in frames
    ]
    large_frames[0].save(
        output_large, "WEBP", save_all=True, append_images=large_frames[1:],
        duration=[frame_duration] * len(large_frames), loop=0,
    )


def _format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


