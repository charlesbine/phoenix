from enum import Enum


class AppStatus(Enum):
    """Application status"""

    SKIP = "skip"
    PRIORITIZE = "prioritize"
    NORMAL = "normal"
