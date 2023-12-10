import enum

class AppStatus(enum.Enum):
    """Application status"""
    SKIP = "skip"
    PRIORITIZE = "prioritize"
    NORMAL = "normal"