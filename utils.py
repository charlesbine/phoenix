from pathlib import Path


def output_dir() -> Path:
    return Path(__file__).parent / "outputs"


def apps_dir() -> Path:
    return Path(__file__).parent / "apps"
