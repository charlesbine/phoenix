from pathlib import Path


def output_dir() -> Path:
    return Path(__file__).parent / "outputs"


def apps_dir() -> Path:
    return Path(__file__).parent / "apps"


def get_downloaded_app_names() -> list[str]:
    return [p.stem for p in apps_dir().glob("*.star")]