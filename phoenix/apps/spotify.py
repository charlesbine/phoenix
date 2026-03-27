"""Spotify Now Playing — pulls from Home Assistant media_player entity.

Two alternating frames:
1. Full-screen album art (64x64)
2. Song info via pixlet: album art, title (marquee), artist, progress bar
"""

import base64
import io
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from phoenix.cache import cache_get
from phoenix.paths import DATA_DIR, ensure_dirs
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

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
    for entity_id in MEDIA_PLAYER_ENTITIES:
        data = _fetch_entity(entity_id, settings)
        if data.get("state") == "playing":
            return data
    return None


def _download_art(url: str, settings: Settings) -> Image.Image | None:
    if not url:
        return None
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


def _format_time(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def render(settings: Settings, config: dict[str, str], output: Path, output_large: Path) -> None:
    ensure_dirs()

    player = _find_playing(settings)
    if player is None:
        for f in [output, output_large]:
            if f.exists():
                f.unlink()
        return

    attrs = player.get("attributes", {})
    title = attrs.get("media_title", "Unknown")
    artist = attrs.get("media_artist", "Unknown")
    album = attrs.get("media_album_name", "")
    duration = attrs.get("media_duration", 0)
    position = attrs.get("media_position", 0)
    position_updated = attrs.get("media_position_updated_at", "")
    art_url = attrs.get("entity_picture", "")

    # Extrapolate current position
    if position_updated and duration > 0:
        try:
            from datetime import datetime, timezone
            updated_at = datetime.fromisoformat(position_updated)
            now = datetime.now(timezone.utc)
            elapsed = (now - updated_at).total_seconds()
            position = min(position + elapsed, duration)
        except Exception:
            pass

    progress_pct = position / duration if duration > 0 else 0

    # Download album art
    art = _download_art(art_url, settings)

    # Frame 1: Full-screen album art
    frame_art = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    if art:
        frame_art.paste(art.resize((64, 64), Image.Resampling.LANCZOS), (0, 0))

    # Frame 2: Info frame via pixlet
    # Encode album art as base64 PNG for embedding in starlark
    art_b64 = ""
    if art:
        buf = io.BytesIO()
        art.resize((28, 28), Image.Resampling.LANCZOS).save(buf, "PNG")
        art_b64 = base64.b64encode(buf.getvalue()).decode()

    # Progress bar: 58px wide area
    bar_filled = max(1, int(58 * progress_pct)) if progress_pct > 0 else 0

    star = f'''load("render.star", "render")
load("encoding/base64.star", "base64")

ART = "{art_b64}"

def main():
    children = []

    # Song title — full width, Spotify green, big font
    children.append(
        render.Padding(
            pad = (3, 4, 3, 0),
            child = render.Marquee(
                width = 58,
                child = render.Text("{_escape(title)}", font = "6x13", color = "#1DB954"),
            ),
        )
    )

    children.append(render.Box(width = 64, height = 3))

    # Album art + artist/album
    art_and_info = []
    if ART:
        art_and_info.append(
            render.Padding(
                pad = (3, 0, 3, 0),
                child = render.Image(src = base64.decode(ART), width = 24, height = 24),
            )
        )
    art_and_info.append(
        render.Column(
            main_align = "center",
            expanded = True,
            children = [
                render.Marquee(
                    width = 30,
                    child = render.Text("{_escape(artist)}", font = "tom-thumb", color = "#FFFFFF"),
                ),
                render.Box(width = 1, height = 2),
                render.Marquee(
                    width = 30,
                    child = render.Text("{_escape(album)}", font = "tom-thumb", color = "#666666"),
                ),
            ],
        )
    )
    children.append(
        render.Box(
            width = 64,
            height = 24,
            child = render.Row(
                cross_align = "center",
                children = art_and_info,
            ),
        )
    )

    # Time row
    children.append(
        render.Padding(
            pad = (3, 3, 3, 0),
            child = render.Row(
                expanded = True,
                main_align = "space_between",
                children = [
                    render.Text("{_format_time(position)}", font = "tom-thumb", color = "#1DB954"),
                    render.Text("{_format_time(duration)}", font = "tom-thumb", color = "#444444"),
                ],
            ),
        )
    )

    # Progress bar below times
    children.append(
        render.Padding(
            pad = (3, 2, 3, 0),
            child = render.Stack(
                children = [
                    render.Box(width = 58, height = 3, color = "#282828"),
                    render.Box(width = {bar_filled}, height = 3, color = "#1DB954"),
                ],
            ),
        )
    )

    return render.Root(
        child = render.Column(
            children = children,
        ),
    )
'''

    frame_info = None
    with tempfile.TemporaryDirectory() as tmp:
        star_path = Path(tmp) / "spotify_info.star"
        star_path.write_text(star)
        for is_large in [False, True]:
            tmp_out = Path(tmp) / ("info_large.webp" if is_large else "info.webp")
            cmd = [
                "pixlet", "render", str(star_path),
                "-o", str(tmp_out),
                "-w", str(settings.render_width),
                "-t", str(settings.render_height),
            ]
            if is_large:
                cmd.extend(["-m", str(settings.magnification)])
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                logger.warning("[spotify] pixlet info frame failed: %s", proc.stderr[:200])

        info_path = Path(tmp) / "info.webp"
        info_large_path = Path(tmp) / "info_large.webp"

        if info_path.exists():
            frame_info = Image.open(info_path).convert("RGBA").copy()

    if frame_info is None:
        frame_info = frame_art.copy()

    # Save animated webp — 5s per frame
    frame_duration = 5000
    frames = [frame_art, frame_info]

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


def _escape(s: str) -> str:
    """Escape string for embedding in Starlark string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
