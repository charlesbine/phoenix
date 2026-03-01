"""Community app browsing and importing. Uses subprocess for git operations."""

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CommunityApp:
    name: str
    summary: str
    path: Path


def ensure_repo(repo_path: Path) -> None:
    """Clone or pull the Tidbyt community repo."""
    if (repo_path / ".git").exists():
        logger.info("Pulling community repo at %s", repo_path)
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path,
            capture_output=True,
            check=False,
        )
    else:
        logger.info("Cloning community repo to %s", repo_path)
        subprocess.run(
            ["git", "clone", "https://github.com/tidbyt/community.git", str(repo_path)],
            capture_output=True,
            check=True,
        )


def list_apps(repo_path: Path) -> list[CommunityApp]:
    """List all community apps from the repo."""
    apps_dir = repo_path / "apps"
    if not apps_dir.exists():
        return []

    results: list[CommunityApp] = []
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        manifest = app_dir / "manifest.yaml"
        if not manifest.exists():
            continue
        try:
            meta = yaml.safe_load(manifest.read_text())
            results.append(CommunityApp(
                name=meta.get("id", app_dir.name),
                summary=meta.get("summary", ""),
                path=app_dir,
            ))
        except Exception:
            results.append(CommunityApp(name=app_dir.name, summary="", path=app_dir))

    return results


def get_manifest(repo_path: Path, name: str) -> dict:
    """Read the manifest.yaml for a community app."""
    manifest = repo_path / "apps" / name / "manifest.yaml"
    if not manifest.exists():
        raise ValueError(f"Community app '{name}' not found")
    return yaml.safe_load(manifest.read_text())


def import_app(repo_path: Path, name: str, dest: Path) -> Path:
    """Copy a community app's .star file to the local apps directory."""
    app_dir = repo_path / "apps" / name
    if not app_dir.exists():
        raise ValueError(f"Community app '{name}' not found in {repo_path}")

    star_files = list(app_dir.glob("*.star"))
    if not star_files:
        raise ValueError(f"No .star file found in {app_dir}")

    src = star_files[0]
    dst = dest / f"{name}.star"
    shutil.copy(src, dst)
    logger.info("Imported %s -> %s", src.name, dst)
    return dst
