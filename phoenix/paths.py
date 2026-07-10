"""Central path definitions for all Phoenix directories and file locations."""

from pathlib import Path

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

DB_PATH = PACKAGE_DIR / "phoenix.db"

COMMUNITY_DIR = REPO_DIR / "community"


def ensure_dirs() -> None:
    """Create runtime directories if they don't exist."""
    for d in (DATA_DIR, OUTPUTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def star_path(name: str) -> Path:
    # Check flat file first, then subdirectory (community apps with assets)
    flat = APPS_DIR / f"{name}.star"
    if flat.exists():
        return flat
    subdir = APPS_DIR / name / f"{name}.star"
    if subdir.exists():
        return subdir
    return flat  # default for new apps


def python_app_path(name: str) -> Path:
    return APPS_DIR / f"{name}.py"


def static_app_path(name: str) -> Path | None:
    """Find a static image file (webp, gif, png, apng) for an app."""
    for ext in (".webp", ".gif", ".png", ".apng"):
        p = APPS_DIR / f"{name}{ext}"
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
    return base / (f"current_app__{device_id}.txt" if device_id else "current_app.txt")


def current_display_file(device_id: str | None = None) -> Path:
    """The last frame a device showed, copied for the web/dashboard preview."""
    base = DATA_DIR / "output"
    return base / (f"current_display__{device_id}.webp" if device_id else "current_display.webp")


def show_now_file(device_id: str | None = None) -> Path:
    """Sentinel asking a device to jump to a named app immediately."""
    base = DATA_DIR / "output"
    return base / (f"show_now__{device_id}.txt" if device_id else "show_now.txt")


def output_path(name: str) -> Path:
    return OUTPUTS_DIR / f"{name}.webp"


def output_path_large(name: str) -> Path:
    return OUTPUTS_DIR / f"{name}.large.webp"


def data_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def preprocessor_module(name: str) -> str:
    return f"phoenix.preprocessors.{name}"


def has_preprocessor(name: str) -> bool:
    return (PREPROCESSORS_DIR / f"{name}.py").exists()
