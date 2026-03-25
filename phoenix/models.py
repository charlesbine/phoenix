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


class AppConfig(BaseModel):
    name: str
    enabled: bool = True
    active: bool = True
    refresh_interval: timedelta = timedelta(minutes=1)
    last_updated: datetime | None = None
    pixlet_config: dict[str, str] = {}
    priority: int = 0
    sort_order: int = 0

    def is_stale(self, factor: float = 1.5) -> bool:
        if self.last_updated is None:
            return True
        elapsed = datetime.now() - self.last_updated
        return elapsed > self.refresh_interval * factor

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
