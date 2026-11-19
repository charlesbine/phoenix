"""Community app browsing and importing from charlesbine/phoenix-apps."""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

COMMUNITY_REPO = "https://github.com/charlesbine/phoenix-apps.git"
_repo_lock = Lock()


@dataclass
class CommunityApp:
    name: str
    summary: str
    description: str
    author: str
    file_name: str
    path: Path
    category: str = ""
    tags: list[str] = field(default_factory=list)
    supports_2x: bool = False


def ensure_repo(repo_path: Path, *, refresh: bool = True) -> None:
    """Initialize the catalog on demand, and refresh it when requested."""
    with _repo_lock:
        git_dir = repo_path / ".git"
        if git_dir.exists():
            if refresh:
                logger.info("Pulling community repo at %s", repo_path)
                subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=repo_path, capture_output=True, check=True, timeout=60,
                )
            return

        logger.info("Cloning community repo to %s", repo_path)
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        # The list and category requests can arrive together. Publish only
        # a completed clone, so a failed or interrupted one can be retried.
        with TemporaryDirectory(dir=repo_path.parent, prefix=".community-") as staging:
            checkout = Path(staging) / "catalog"
            subprocess.run(
                ["git", "clone", "--depth=1", COMMUNITY_REPO, str(checkout)],
                capture_output=True, check=True, timeout=60,
            )
            try:
                checkout.rename(repo_path)
            except OSError:
                if not git_dir.exists():
                    raise


def _parse_app(app_dir: Path) -> CommunityApp | None:
    """Parse a single app directory into a CommunityApp."""
    manifest = app_dir / "manifest.yaml"
    if not manifest.exists():
        return None
    try:
        meta = yaml.safe_load(manifest.read_text())
        return CommunityApp(
            name=meta.get("id", app_dir.name),
            summary=meta.get("summary", ""),
            description=meta.get("desc", ""),
            author=meta.get("author", ""),
            file_name=meta.get("fileName", ""),
            path=app_dir,
            category=meta.get("category", ""),
            tags=meta.get("tags", []) or [],
            supports_2x=bool(meta.get("supports2x", False)),
        )
    except Exception:
        logger.debug("Failed to parse manifest for %s", app_dir.name)
        return None


def list_apps(repo_path: Path) -> list[CommunityApp]:
    """List all community apps from the repo."""
    apps_dir = repo_path / "apps"
    if not apps_dir.exists():
        return []

    results: list[CommunityApp] = []
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        app = _parse_app(app_dir)
        if app is not None:
            results.append(app)
    return results


def list_categories(repo_path: Path) -> list[str]:
    """Return all unique categories sorted alphabetically."""
    cats = {app.category for app in list_apps(repo_path) if app.category}
    return sorted(cats)


def list_tags(repo_path: Path) -> list[str]:
    """Return all unique tags sorted alphabetically."""
    tags: set[str] = set()
    for app in list_apps(repo_path):
        tags.update(app.tags)
    return sorted(tags)


def search_apps(
    repo_path: Path,
    query: str = "",
    category: str = "",
    tag: str = "",
) -> list[CommunityApp]:
    """Search/filter community apps by text query, category, and/or tag."""
    apps = list_apps(repo_path)

    if query:
        q = query.lower()
        apps = [
            a for a in apps
            if q in a.name.lower()
            or q in a.summary.lower()
            or q in a.description.lower()
            or q in a.author.lower()
            or any(q in t.lower() for t in a.tags)
        ]

    if category:
        apps = [a for a in apps if a.category == category]

    if tag:
        apps = [a for a in apps if tag in a.tags]

    return apps


def _resolve_app_dir(repo_path: Path, name: str) -> Path:
    """Resolve a manifest ID or directory name to the actual app directory.

    Tries: exact directory match, then scans manifests for matching id.
    """
    # Direct directory match
    app_dir = repo_path / "apps" / name
    if app_dir.exists():
        return app_dir

    # Scan manifests for matching id (handles fuzzy-clock -> fuzzyclock)
    apps_dir = repo_path / "apps"
    if apps_dir.exists():
        for d in apps_dir.iterdir():
            if not d.is_dir():
                continue
            manifest = d / "manifest.yaml"
            if manifest.exists():
                try:
                    meta = yaml.safe_load(manifest.read_text())
                    if meta.get("id") == name:
                        return d
                except Exception:
                    pass

    raise ValueError(f"Community app '{name}' not found in {repo_path}")


def get_manifest(repo_path: Path, name: str) -> dict:
    """Read the manifest.yaml for a community app."""
    app_dir = _resolve_app_dir(repo_path, name)
    return yaml.safe_load((app_dir / "manifest.yaml").read_text())


def import_app(repo_path: Path, name: str, dest: Path) -> Path:
    """Copy a community app to the local apps directory.

    Apps with asset subdirectories (images/, etc.) get their own directory under
    dest. Simple single-file apps get copied as a flat .star file.
    """
    app_dir = _resolve_app_dir(repo_path, name)

    star_files = list(app_dir.glob("*.star"))
    if not star_files:
        raise ValueError(f"No .star file found in {app_dir}")

    safe_name = name.replace("-", "_")
    has_assets = any(item.is_dir() for item in app_dir.iterdir())

    if has_assets:
        # Copy entire directory: dest/safe_name/
        dst_dir = dest / safe_name
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(app_dir, dst_dir, ignore=shutil.ignore_patterns("manifest.yaml", "*.webp", "*.md"))
        # Rename the .star file to match the safe_name
        for sf in dst_dir.glob("*.star"):
            target = dst_dir / f"{safe_name}.star"
            if sf != target:
                sf.rename(target)
            break
        logger.info("Imported %s (with assets) -> %s", name, dst_dir)
        return dst_dir / f"{safe_name}.star"
    else:
        # Simple app: just copy the .star file
        dst_star = dest / f"{safe_name}.star"
        shutil.copy(star_files[0], dst_star)
        logger.info("Imported %s -> %s", star_files[0].name, dst_star)
        return dst_star
