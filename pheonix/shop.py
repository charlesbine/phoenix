"""
Getting more applets
"""
from pathlib import Path
import yaml

from sh.contrib import git


COMMUNITY_REPO_URL = "git@github.com:tidbyt/community.git"
COMMUNITY_REPO_LOCATION = Path(__file__).parent.parent / "community"


def get_community_repo() -> git.Repo:
    """Get the community repo, cloning it if it doesn't exist."""
    if not COMMUNITY_REPO_LOCATION.exists():
        return git.clone(COMMUNITY_REPO_URL)

    return git.pull(_cwd=COMMUNITY_REPO_LOCATION)


def get_all_community_app_folders() -> list[Path]:
    """Get the names of all the apps in the community repo."""
    app_dir = COMMUNITY_REPO_LOCATION / "apps"
    return sorted([p for p in app_dir.iterdir() if p.is_dir()], key=lambda p: p.name)


def get_all_community_app_names() -> list[str]:
    """Get the names of all the apps in the community repo."""
    return [p.name for p in get_all_community_app_folders()]


def get_community_app_folder(app_name: str) -> Path:
    """Get the path to the app with the given name."""
    return COMMUNITY_REPO_LOCATION / "apps" / app_name


def get_community_app_manifest(app_name: str) -> dict:
    """Get the manifest for the app with the given name."""
    manifest_path = get_community_app_folder(app_name) / "manifest.yaml"
    return yaml.safe_load(manifest_path.read_text())


def get_community_app_starlark_path(app_name: str) -> Path:
    """Get the path to the starlark file for the app with the given name."""
    filename = get_community_app_manifest(app_name)["fileName"]
    return get_community_app_folder(app_name) / filename