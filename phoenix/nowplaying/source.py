"""Now-playing data sources.

HANowPlayingSource polls Home Assistant media_player entities (the same source
the old spotify app used) at a slow interval and hands back a Track whose
position extrapolates locally between polls — so the progress bar moves smoothly
at the render rate without hammering HA. Album art is downloaded once per track.
"""

import io
import logging
import time
from dataclasses import dataclass, field

from PIL import Image

from phoenix.cache import cache_get
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

# Checked in order; first one 'playing' wins.
MEDIA_PLAYER_ENTITIES = [
    "media_player.spotify_charlesbine",
    "media_player.unnamed_room",
    "media_player.living_room",
    "media_player.bedroom",
    "media_player.bathroom",
    "media_player.kitchen",
]


@dataclass
class Track:
    title: str = ""
    artist: str = ""
    album: str = ""
    art: Image.Image | None = None
    duration: float = 0.0
    playing: bool = False
    _position: float = 0.0
    _captured_at: float = field(default_factory=time.monotonic)

    @property
    def key(self) -> str:
        return f"{self.title}␟{self.artist}"

    def position_now(self) -> float:
        """Position extrapolated to this instant (smooth between polls)."""
        pos = self._position
        if self.playing:
            pos += time.monotonic() - self._captured_at
        return min(pos, self.duration) if self.duration else pos

    def progress(self) -> float:
        return (self.position_now() / self.duration) if self.duration > 0 else 0.0


class HANowPlayingSource:
    def __init__(self, settings: Settings, poll: float = 3.0):
        self._settings = settings
        self._poll = poll
        self._last_poll = 0.0
        self._track: Track | None = None

    def _fetch_entity(self, entity_id: str) -> dict:
        url = f"{self._settings.ha_url.rstrip('/')}/api/states/{entity_id}"
        headers = {"Authorization": f"Bearer {self._settings.ha_token}"}
        try:
            status, body, _ = cache_get(url, ttl=2, headers=headers)
            if status == 200:
                import json

                return json.loads(body)
        except Exception:
            pass
        return {}

    def _find_playing(self) -> dict | None:
        for entity_id in MEDIA_PLAYER_ENTITIES:
            data = self._fetch_entity(entity_id)
            if data.get("state") == "playing":
                return data
        return None

    def _download_art(self, url: str) -> Image.Image | None:
        if not url:
            return None
        if url.startswith("/"):
            url = f"{self._settings.ha_url.rstrip('/')}{url}"
        try:
            headers = {"Authorization": f"Bearer {self._settings.ha_token}"}
            status, body, _ = cache_get(url, ttl=300, headers=headers)
            if status == 200 and body:
                return Image.open(io.BytesIO(body)).convert("RGB")
        except Exception:
            logger.debug("[nowplaying] album art download failed")
        return None

    def get(self) -> Track | None:
        """Current track, polling HA at most every `poll` seconds."""
        now = time.monotonic()
        if self._track is not None and now - self._last_poll < self._poll:
            return self._track
        self._last_poll = now

        player = self._find_playing()
        if player is None:
            self._track = None
            return None

        attrs = player.get("attributes", {})
        title = attrs.get("media_title", "") or ""
        artist = attrs.get("media_artist", "") or ""
        duration = float(attrs.get("media_duration", 0) or 0)
        position = float(attrs.get("media_position", 0) or 0)

        # HA gives position as-of media_position_updated_at — extrapolate to now.
        updated = attrs.get("media_position_updated_at", "")
        if updated and duration > 0:
            try:
                from datetime import datetime, timezone

                dt = (datetime.now(timezone.utc) - datetime.fromisoformat(updated)).total_seconds()
                position = min(position + max(0.0, dt), duration)
            except Exception:
                pass

        key = f"{title}␟{artist}"
        art = self._track.art if (self._track and self._track.key == key) else self._download_art(
            attrs.get("entity_picture", "")
        )

        self._track = Track(
            title=title,
            artist=artist,
            album=attrs.get("media_album_name", "") or "",
            art=art,
            duration=duration,
            playing=True,
            _position=position,
            _captured_at=now,
        )
        return self._track
