"""Central path definitions for all Phoenix directories and file locations."""

import os
import re
from pathlib import Path

IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,127}$")


def is_valid_identifier(value: str) -> bool:
    """Return True if value is a safe Phoenix identifier (app, panel, device, playlist, store slug)."""
    return isinstance(value, str) and IDENTIFIER_RE.fullmatch(value) is not None


def require_identifier(value: str, label: str = "identifier") -> str:
    """Validate an identifier against path traversal and special characters."""
    if not is_valid_identifier(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def ensure_within(base: Path, target: Path, label: str = "path") -> Path:
    """Defense-in-depth check that target resolves inside base."""
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    if not target_resolved.is_relative_to(base_resolved):
        raise ValueError(f"{label} escapes {base_resolved}")
    return target

PACKAGE_DIR = Path(__file__).parent
REPO_DIR = PACKAGE_DIR.parent
APPS_DIR = PACKAGE_DIR / "apps"
DATA_DIR = PACKAGE_DIR / "data"
OUTPUTS_DIR = PACKAGE_DIR / "outputs"
PREPROCESSORS_DIR = PACKAGE_DIR / "preprocessors"
ASSETS_DIR = PREPROCESSORS_DIR / "assets"
TEMPLATES_DIR = PACKAGE_DIR / "templates"
FRONTEND_DIR = REPO_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

DB_PATH = Path(os.environ.get("PHOENIX_DB_PATH") or PACKAGE_DIR / "phoenix.db")

COMMUNITY_DIR = REPO_DIR / "community"


def ensure_dirs() -> None:
    """Create runtime directories if they don't exist."""
    for d in (DATA_DIR, OUTPUTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def star_path(name: str) -> Path:
    require_identifier(name, "app name")
    # Check flat file first, then subdirectory (community apps with assets)
    flat = ensure_within(APPS_DIR, APPS_DIR / f"{name}.star", "app path")
    if flat.exists():
        return flat
    subdir = ensure_within(APPS_DIR, APPS_DIR / name / f"{name}.star", "app path")
    if subdir.exists():
        return subdir
    return flat  # default for new apps


def python_app_path(name: str) -> Path:
    require_identifier(name, "app name")
    return ensure_within(APPS_DIR, APPS_DIR / f"{name}.py", "app path")


def static_app_path(name: str) -> Path | None:
    """Find a static image file (webp, gif, png, apng) for an app."""
    require_identifier(name, "app name")
    for ext in (".webp", ".gif", ".png", ".apng"):
        p = ensure_within(APPS_DIR, APPS_DIR / f"{name}{ext}", "app path")
        if p.exists():
            return p
    return None


def app_type(name: str) -> str:
    """Determine the app type: 'star', 'python', 'static', or 'unknown'."""
    if star_path(name).exists():
        return "star"
    if python_app_path(name).exists():
        return "python"
    if static_app_path(name) is not None:
        return "static"
    return "unknown"


def current_app_file(device_id: str | None = None) -> Path:
    """Sentinel naming the app a device is currently showing.

    Unsuffixed (device_id=None) is the legacy single-device file the dashboard
    still reads; per-device files let a mirror follow its target and let the
    dashboard report now-playing per panel.
    """
    base = DATA_DIR / "output"
    if device_id:
        require_identifier(device_id, "device id")
        return ensure_within(base, base / f"current_app__{device_id}.txt", "device sentinel path")
    return base / "current_app.txt"


def current_display_file(device_id: str | None = None) -> Path:
    """The last frame a device showed, copied for the web/dashboard preview."""
    base = DATA_DIR / "output"
    if device_id:
        require_identifier(device_id, "device id")
        return ensure_within(base, base / f"current_display__{device_id}.webp", "device display path")
    return base / "current_display.webp"


def show_now_file(device_id: str | None = None) -> Path:
    """Sentinel asking a device to jump to a named app immediately."""
    base = DATA_DIR / "output"
    if device_id:
        require_identifier(device_id, "device id")
        return ensure_within(base, base / f"show_now__{device_id}.txt", "device sentinel path")
    return base / "show_now.txt"


def output_path(name: str) -> Path:
    require_identifier(name, "app name")
    return ensure_within(OUTPUTS_DIR, OUTPUTS_DIR / f"{name}.webp", "output path")


def output_path_large(name: str) -> Path:
    require_identifier(name, "app name")
    return ensure_within(OUTPUTS_DIR, OUTPUTS_DIR / f"{name}.large.webp", "output path")


def data_path(name: str) -> Path:
    require_identifier(name, "data name")
    return ensure_within(DATA_DIR, DATA_DIR / f"{name}.json", "data path")


def preprocessor_module(name: str) -> str:
    require_identifier(name, "preprocessor name")
    return f"phoenix.preprocessors.{name}"


def has_preprocessor(name: str) -> bool:
    require_identifier(name, "preprocessor name")
    return ensure_within(PREPROCESSORS_DIR, PREPROCESSORS_DIR / f"{name}.py", "preprocessor path").exists()
