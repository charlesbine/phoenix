"""Spotify now-playing preprocessor. Fetches current playback via spotipy."""

import json
import logging

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

from phoenix.models import AppStatus, PreprocessorResult
from phoenix.paths import data_path
from phoenix.settings import Settings

logger = logging.getLogger(__name__)


def run(settings: Settings) -> PreprocessorResult:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        logger.debug("Spotify credentials not configured, skipping")
        return PreprocessorResult(data=None, status=AppStatus.SKIP)

    try:
        sp = Spotify(auth_manager=SpotifyOAuth(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
            redirect_uri=settings.spotify_redirect_uri,
            scope="user-read-playback-state",
            open_browser=False,
        ))

        playback = sp.current_playback()

        if not playback or not playback.get("is_playing"):
            logger.debug("Nothing playing on Spotify")
            return PreprocessorResult(data=None, status=AppStatus.SKIP)

        item = playback.get("item")
        if item is None:
            return PreprocessorResult(data=None, status=AppStatus.SKIP)

        # Get the smallest album art (64x64 is ideal for the matrix)
        images = item.get("album", {}).get("images", [])
        album_art_url = images[-1]["url"] if images else ""

        data = {
            "track": item["name"],
            "artist": item["artists"][0]["name"] if item.get("artists") else "Unknown",
            "album": item.get("album", {}).get("name", ""),
            "album_art_url": album_art_url,
            "is_playing": True,
        }

        data_path("spotify").write_text(json.dumps(data))
        logger.info("Spotify: %s - %s", data["artist"], data["track"])
        return PreprocessorResult(data=data, status=AppStatus.PRIORITIZE, priority=10)

    except Exception:
        logger.exception("Spotify preprocessor error")
        # Don't disable on transient errors — just skip this cycle
        return PreprocessorResult(data=None, status=AppStatus.SKIP)
