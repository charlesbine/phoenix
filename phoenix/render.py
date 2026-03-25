"""Render pipeline: scheduling loop and pixlet subprocess orchestration."""

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from time import sleep

from phoenix.db import AppDatabase
from phoenix.models import AppConfig, AppStatus, PreprocessorResult
from phoenix.paths import ensure_dirs, output_path, output_path_large, star_path
from phoenix.preprocessors import get_preprocessor
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

MAX_TIME_BETWEEN_UPDATES = timedelta(seconds=30)


def run_app(name: str, settings: Settings, app_db: AppDatabase) -> None:
    """Render a single app by name."""
    app = app_db.get(name)
    if app is None:
        raise ValueError(f"App '{name}' not found in database")

    if not app.enabled:
        logger.debug("[%s] Skipping disabled app", name)
        return

    app_star = star_path(name)
    if not app_star.exists():
        raise ValueError(f"Starlark file not found: {app_star}")

    # Run preprocessor if one exists
    preprocessor = get_preprocessor(name)
    if preprocessor is not None:
        logger.info("[%s] Running preprocessor", name)
        try:
            result = preprocessor(settings)
            assert isinstance(result, PreprocessorResult)
            logger.debug("[%s] Preprocessor: status=%s, priority=%s", name, result.status, result.priority)
        except Exception:
            logger.exception("[%s] Preprocessor failed", name)
            result = PreprocessorResult(None, AppStatus.ERROR)

        _handle_preprocessor_result(name, result, app_db)
        if result.status in (AppStatus.DISABLE, AppStatus.SKIP, AppStatus.ERROR):
            return

    # Render normal and large versions
    ensure_dirs()
    logger.info("[%s] Rendering applet", name)
    _run_pixlet(app, settings, large=False)
    _run_pixlet(app, settings, large=True)

    app_db.upsert(name, last_updated=datetime.now())


def _check_pixlet() -> None:
    """Verify pixlet is installed and accessible."""
    if shutil.which("pixlet") is None:
        raise RuntimeError(
            "pixlet not found on PATH. Install it from https://tidbyt.dev/docs/build/installing-pixlet"
        )


def run_all_apps(settings: Settings, app_db: AppDatabase) -> None:
    """Continuous rendering loop. Schedules apps based on refresh intervals."""
    _check_pixlet()
    ensure_dirs()
    while True:
        apps = [a for a in app_db.list_apps() if a.enabled]
        if not apps:
            logger.warning("No enabled apps found, waiting...")
            sleep(MAX_TIME_BETWEEN_UPDATES.total_seconds())
            continue

        apps.sort(key=lambda a: a.priority, reverse=True)

        def next_update_time(app: AppConfig) -> datetime:
            if app.last_updated is None:
                return datetime.now()
            return app.last_updated + app.refresh_interval

        next_app = min(apps, key=next_update_time)
        wait = (next_update_time(next_app) - datetime.now()).total_seconds()

        if wait > MAX_TIME_BETWEEN_UPDATES.total_seconds():
            logger.debug("Nothing to update for %ss, checking again then", MAX_TIME_BETWEEN_UPDATES.total_seconds())
            sleep(MAX_TIME_BETWEEN_UPDATES.total_seconds())
            continue

        wait = max(wait, 0)
        if wait > 0:
            logger.debug("Next: %s in %.1fs", next_app.name, wait)
            sleep(wait)

        try:
            run_app(next_app.name, settings, app_db)
        except Exception:
            logger.exception("[%s] Render failed", next_app.name)


def _handle_preprocessor_result(name: str, result: PreprocessorResult, app_db: AppDatabase) -> None:
    """Update app state based on preprocessor result."""
    if result.status in (AppStatus.DISABLE, AppStatus.ERROR):
        logger.warning("[%s] Preprocessor returned %s, disabling", name, result.status)
        app_db.upsert(name, enabled=False, priority=0)

    if result.status in (AppStatus.DISABLE, AppStatus.SKIP, AppStatus.ERROR):
        # Clean up old output files
        for path in (output_path(name), output_path_large(name)):
            if path.exists():
                logger.info("[%s] Removing stale output: %s", name, path.name)
                path.unlink()
        return

    if result.status == AppStatus.PRIORITIZE:
        app_db.upsert(name, priority=result.priority)
    else:
        app_db.upsert(name, priority=0)


def _run_pixlet(app: AppConfig, settings: Settings, large: bool = False) -> None:
    """Shell out to pixlet to render a Starlark app to .webp.

    Copies the .star file to a temp dir first as a workaround for a pixlet bug:
    https://discuss.tidbyt.com/t/strange-behavior-with-pixlet/6525
    """
    app_star = star_path(app.name)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_star = shutil.copy(app_star, tmp)

        if large:
            out = output_path_large(app.name)
        else:
            out = output_path(app.name)

        cmd = [
            "pixlet", "render", str(tmp_star),
            "-o", str(out),
            "-w", str(settings.render_width),
            "-t", str(settings.render_height),
        ]
        if large:
            cmd.extend(["-m", str(settings.magnification)])

        for key, value in app.pixlet_config.items():
            cmd.append(f"{key}={value}")

        logger.debug("[%s] pixlet: %s", app.name, " ".join(cmd))
        proc = subprocess.run(cmd, env=os.environ, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.error("[%s] pixlet failed (rc=%d): %s", app.name, proc.returncode, proc.stderr)
            raise RuntimeError(f"pixlet render failed for {app.name}")
