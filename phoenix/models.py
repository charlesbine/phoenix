"""Pydantic v2 models for app configuration, display config, and shared types."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


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


class DisplayConfig(BaseModel):
    layout_mode: Literal["cycle", "single", "random"] = "cycle"
    cycle_interval: int = 10
    brightness: int = 255  # 0-255
