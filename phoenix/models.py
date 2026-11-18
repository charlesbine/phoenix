"""Pydantic v2 models for app configuration, display config, and shared types."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from math import cos, pi, radians, sin
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator


class AppStatus(str, Enum):
    NORMAL = "normal"
    SKIP = "skip"
    DISABLE = "disable"
    PRIORITIZE = "prioritize"
    ERROR = "error"


@dataclass
class PreprocessorResult:
    data: Any
    status: AppStatus = AppStatus.NORMAL
    priority: int = 0


# Refresh presets: how often an app should re-render
REFRESH_PRESETS: dict[str, timedelta] = {
    "realtime": timedelta(seconds=30),     # clocks, live data
    "frequent": timedelta(minutes=5),      # sensors, API dashboards
    "ambient": timedelta(minutes=30),      # art, procedural, static content
}

# Default preset assignments based on app name patterns
_DEFAULT_PRESET_PATTERNS: dict[str, list[str]] = {
    "realtime": ["clock", "fuzzy_clock"],
    "ambient": ["procedural_planet", "pixel_planet", "aquarium", "nyan_cat",
                "programming_excuses", "life", "maps", "hello_world",
                "schema_hello_world", "font-preview", "quadrants"],
    # Everything else defaults to "frequent"
}


def default_preset_for(name: str) -> str:
    """Guess the best refresh preset for an app by name."""
    for preset, patterns in _DEFAULT_PRESET_PATTERNS.items():
        if name in patterns:
            return preset
    return "frequent"


class AppConfig(BaseModel):
    name: str
    enabled: bool = True
    active: bool = True
    refresh_interval: timedelta = timedelta(minutes=1)
    last_updated: datetime | None = None
    pixlet_config: dict[str, str] = {}
    priority: int = 0
    sort_order: int = 0
    source: str = ""  # e.g. "community" for tronbyt/apps imports
    runtime: str = ""  # empty = file-backed; otherwise a built-in executor name

    @property
    def refresh_preset(self) -> str:
        """Infer the preset from the current refresh_interval."""
        secs = self.refresh_interval.total_seconds()
        if secs <= 60:
            return "realtime"
        elif secs <= 300:
            return "frequent"
        else:
            return "ambient"

    def seconds_until_refresh(self) -> float:
        if self.last_updated is None:
            return 0.0
        elapsed = datetime.now() - self.last_updated
        remaining = self.refresh_interval - elapsed
        return max(0.0, remaining.total_seconds())

    def is_stale(self) -> bool:
        return self.seconds_until_refresh() == 0.0


class DisplayConfig(BaseModel):
    layout_mode: Literal["cycle", "single", "random"] = "cycle"
    cycle_interval: int = 10
    brightness: int = 255  # 0-255


BRIGHTNESS_SCHEDULE_BACKENDS = {"serial", "wled"}

# Labels used by the dashboard without loading the optional audio runtime.
SPECTROGRAM_PALETTE_OPTIONS = (
    ("hue", "Hue heat"), ("fire", "Fire"), ("ice", "Ice"), ("aurora", "Aurora"), ("mono", "Mono"),
)


class BrightnessStep(BaseModel):
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    brightness: int = Field(strict=True, ge=0, le=255)


class DisplaySettings(BaseModel):
    timezone: str = "UTC"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Choose a valid time zone") from None
        return value

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude")
        return self

    def local_time(self, now: datetime | None = None) -> datetime:
        zone = ZoneInfo(self.timezone)
        return now.astimezone(zone) if now is not None else datetime.now(zone)


@lru_cache(maxsize=16)
def _sun_above_horizon(utc_minute: datetime, latitude: float, longitude: float) -> bool:
    """NOAA's approximate solar position, with the conventional sunrise horizon."""
    utc_hours = utc_minute.hour + utc_minute.minute / 60
    days_in_year = datetime(utc_minute.year, 12, 31).timetuple().tm_yday
    year_angle = 2 * pi / days_in_year * (utc_minute.timetuple().tm_yday - 1 + (utc_hours - 12) / 24)
    equation_of_time = 229.18 * (
        0.000075 + 0.001868 * cos(year_angle) - 0.032077 * sin(year_angle)
        - 0.014615 * cos(2 * year_angle) - 0.040849 * sin(2 * year_angle)
    )
    declination = (
        0.006918 - 0.399912 * cos(year_angle) + 0.070257 * sin(year_angle)
        - 0.006758 * cos(2 * year_angle) + 0.000907 * sin(2 * year_angle)
        - 0.002697 * cos(3 * year_angle) + 0.00148 * sin(3 * year_angle)
    )
    hour_angle = radians((utc_hours * 60 + equation_of_time + 4 * longitude) % 1440 / 4 - 180)
    lat = radians(latitude)
    altitude_sine = sin(lat) * sin(declination) + cos(lat) * cos(declination) * cos(hour_angle)
    return altitude_sine >= sin(radians(-0.833))


class BrightnessSchedule(BaseModel):
    enabled: bool = False
    mode: Literal["night", "custom"] = "custom"
    steps: list[BrightnessStep] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def validate_steps(self) -> Self:
        if self.enabled and self.mode == "custom" and not self.steps:
            raise ValueError("Add a time before enabling the custom schedule")
        if len({step.time for step in self.steps}) != len(self.steps):
            raise ValueError("Each scheduled time must be unique")
        self.steps.sort(key=lambda step: step.time)
        return self

    def level_at(self, settings: DisplaySettings, brightness: int, now: datetime | None = None) -> int:
        if not self.enabled:
            return brightness
        local = settings.local_time(now)
        if self.mode == "custom":
            hhmm = local.strftime("%H:%M")
            return next((step.brightness for step in reversed(self.steps) if step.time <= hhmm),
                        self.steps[-1].brightness)

        if brightness == 0:
            return 0
        off_start, off_end = (2, 9) if local.weekday() >= 5 else (0, 8)
        if off_start <= local.hour < off_end:
            return 0
        if settings.latitude is not None and settings.longitude is not None:
            utc_minute = local.astimezone(timezone.utc).replace(second=0, microsecond=0)
            daylight = _sun_above_horizon(utc_minute, settings.latitude, settings.longitude)
        else:
            daylight = 7 <= local.hour < 19
        return brightness if daylight else max(1, round(brightness / 4))


def brightness_schedule_for(device: dict) -> BrightnessSchedule | None:
    if device["backend"] not in BRIGHTNESS_SCHEDULE_BACKENDS:
        return None
    serialized = device.get("brightness_schedule")
    if serialized:
        return BrightnessSchedule.model_validate_json(serialized)
    return BrightnessSchedule(enabled=True, mode="night")


def display_settings_from_json(serialized: str | None) -> DisplaySettings:
    return DisplaySettings.model_validate_json(serialized) if serialized else DisplaySettings()


def device_brightness(device: dict) -> int:
    schedule = brightness_schedule_for(device)
    if schedule is None or not schedule.enabled:
        return device["brightness"]
    return schedule.level_at(display_settings_from_json(device.get("display_settings")), device["brightness"])
