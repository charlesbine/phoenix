from enum import Enum
from dataclasses import dataclass
from typing import Any


class AppStatus(Enum):
    """Application status"""

    # The preprocessor wants to skip the app
    SKIP = "skip"

    # The preprocessor wants to disable the app
    DISABLE = "disable"

    # The preprocessor wants to prioritize the app
    PRIORITIZE = "prioritize"

    # The preprocessor wants to display the app normally
    NORMAL = "normal"

    # The preprocessor encountered an error, should be disabled / not reran
    ERROR = "error"


@dataclass
class PreprocessorResult:
    """Result from a preprocessor function."""
    data: Any
    status: AppStatus = AppStatus.NORMAL
    priority: int = 0
