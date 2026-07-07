"""Single source of truth for all static configuration. Loads from .env and environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHOENIX_", env_file=".env")

    # Platform: "matrix" on Raspberry Pi, "serial" for Matrix Portal M4,
    # "wled" for an ESP32/WLED panel (Apollo M-1) over DNRGB UDP, "web" for dev
    platform: Literal["matrix", "serial", "web", "wled"] = "web"

    # Serial display (Matrix Portal M4)
    serial_port: str = "/dev/ttyACM0"  # Linux (Pi); on macOS use /dev/cu.usbmodem101
    serial_brightness: int = 255  # 0-255, sent to M4 with each frame

    # WLED display (ESP32 / Apollo M-1 over DNRGB realtime UDP)
    wled_ip: str = "auto"  # explicit IP, or "auto" for mDNS discovery (needs the `wled` extra)
    wled_port: int = 21324

    # Audio visualizer capture (host input for the 'audio' content-mode)
    audio_device: str = ""  # PortAudio input name/index; "" = system default (needs the `audio` extra)

    # Rendering
    render_width: int = 64
    render_height: int = 64
    magnification: int = 5

    # Dashboard (also serves preprocessor data, cache proxy at /proxy)
    dashboard_port: int = 7002

    # MQTT
    mqtt_broker: str = ""  # e.g. europa.local — leave empty to disable
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_notify_topic: str = "phoenix/notify"

    # Home Assistant
    ha_url: str = ""  # e.g. http://homeassistant.local:8123
    ha_token: str = ""  # Long-lived access token

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:9090"


def get_settings() -> Settings:
    return Settings()
