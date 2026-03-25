"""Single source of truth for all static configuration. Loads from .env and environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHOENIX_", env_file=".env")

    # Platform: "matrix" on Raspberry Pi, "serial" for Matrix Portal M4, "web" for dev/web viewing
    platform: Literal["matrix", "serial", "web"] = "web"

    # Serial display (Matrix Portal M4)
    serial_port: str = "/dev/ttyACM0"  # Linux (Pi); on macOS use /dev/cu.usbmodem101
    serial_brightness: int = 255  # 0-255, sent to M4 with each frame

    # Rendering
    render_width: int = 64
    render_height: int = 64
    magnification: int = 5

    # Dashboard (also serves preprocessor data at /data/)
    dashboard_port: int = 7002

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:9090"


def get_settings() -> Settings:
    return Settings()
