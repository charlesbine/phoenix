"""Render pipeline: scheduling loop and pixlet subprocess orchestration."""

import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep

from PIL import Image

from phoenix.db import AppDatabase
from phoenix.models import AppConfig, AppStatus, PreprocessorResult
from phoenix.paths import (
    APPS_DIR,
    app_type,
    ensure_dirs,
    output_path,
    output_path_large,
    python_app_path,
    star_path,
    static_app_path,
)
from phoenix.preprocessors import get_preprocessor
from phoenix.settings import Settings

logger = logging.getLogger(__name__)

MAX_TIME_BETWEEN_UPDATES = timedelta(seconds=30)


def _is_panel(name: str) -> bool:
    return name.startswith("panel_")


def _render_dispatch(app: AppConfig, settings: Settings) -> None:
    """Render an app based on its type (star, python, static, or panel)."""
    import time as _time
    ensure_dirs()
    start = _time.perf_counter()

    if _is_panel(app.name):
        logger.info("[%s] Rendering dashboard panel", app.name)
        panel_app = AppConfig(
            name=app.name,
            pixlet_config={"instance_id": app.name.removeprefix("panel_")},
        )
        _run_pixlet(panel_app, settings, large=False, star_override=star_path("dashboard_panel"))
        _run_pixlet(panel_app, settings, large=True, star_override=star_path("dashboard_panel"))
        elapsed = _time.perf_counter() - start
        logger.info("[%s] Render complete (%.2fs)", app.name, elapsed)
        return

    kind = app_type(app.name)
    if kind == "star":
        logger.info("[%s] Rendering starlark applet", app.name)
        _run_pixlet(app, settings, large=False)
        _run_pixlet(app, settings, large=True)
    elif kind == "python":
        logger.info("[%s] Rendering python applet", app.name)
        _run_python_app(app, settings)
    elif kind == "static":
        logger.info("[%s] Copying static image", app.name)
        _copy_static_app(app, settings)
    else:
        raise ValueError(f"No .star, .py, or image file found for '{app.name}' in {APPS_DIR}")

    elapsed = _time.perf_counter() - start
    output_size = output_path(app.name).stat().st_size if output_path(app.name).exists() else 0
    logger.info("[%s] Render complete (%.2fs, %dKB)", app.name, elapsed, output_size // 1024)


def render_preview(name: str, settings: Settings) -> None:
    """Render a preview of an app regardless of DB state. Works for apps not yet registered."""
    if _is_panel(name):
        from phoenix.preprocessors.dashboard_panel import run_panel
        panel_id = name.removeprefix("panel_")
        run_panel(panel_id, settings)
        app = AppConfig(name=name)
        _render_dispatch(app, settings)
        return

    kind = app_type(name)
    if kind == "unknown":
        raise ValueError(f"No app file found for '{name}' in {APPS_DIR}")

    # Run preprocessor if one exists (needed for apps that depend on data files)
    preprocessor = get_preprocessor(name)
    if preprocessor is not None:
        logger.info("[%s] Running preprocessor for preview", name)
        try:
            preprocessor(settings)
        except Exception:
            logger.warning("[%s] Preprocessor failed during preview, continuing anyway", name)

    app = AppConfig(name=name)
    _render_dispatch(app, settings)


def run_app(name: str, settings: Settings, app_db: AppDatabase) -> None:
    """Render a single app by name."""
    app = app_db.get(name)
    if app is None:
        raise ValueError(f"App '{name}' not found in database")

    if not app.enabled:
        logger.debug("[%s] Skipping disabled app", name)
        return

    if not _is_panel(name):
        kind = app_type(name)
        if kind == "unknown":
            raise ValueError(f"No app file found for '{name}' in {APPS_DIR}")

    # Run preprocessor if one exists (panels use their own preprocessor)
    if _is_panel(name):
        from phoenix.preprocessors.dashboard_panel import run_panel
        panel_id = name.removeprefix("panel_")
        logger.info("[%s] Running panel preprocessor", name)
        try:
            result = run_panel(panel_id, settings)
        except Exception:
            logger.exception("[%s] Panel preprocessor failed", name)
            result = PreprocessorResult(None, AppStatus.ERROR)
        _handle_preprocessor_result(name, result, app_db)
        if result.status in (AppStatus.DISABLE, AppStatus.SKIP, AppStatus.ERROR):
            return
        _render_dispatch(app, settings)
        app_db.upsert(name, last_updated=datetime.now())
        return

    # Python apps handle their own data fetching — skip preprocessor
    preprocessor = get_preprocessor(name) if app_type(name) != "python" else None
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

    _render_dispatch(app, settings)
    app_db.upsert(name, last_updated=datetime.now())


def _check_pixlet() -> None:
    """Verify pixlet is installed and accessible."""
    if shutil.which("pixlet") is None:
        raise RuntimeError(
            "pixlet not found on PATH. Install it from https://tidbyt.dev/docs/build/installing-pixlet"
        )


def _is_due(app: AppConfig) -> bool:
    """Check if an app is due for re-rendering."""
    if app.last_updated is None:
        return True
    elapsed = datetime.now() - app.last_updated
    return elapsed >= app.refresh_interval


def _render_one(name: str, settings: Settings, app_db: AppDatabase) -> None:
    """Render a single app with error handling."""
    try:
        run_app(name, settings, app_db)
    except Exception:
        logger.exception("[%s] Render failed", name)
        app_db.upsert(name, last_updated=datetime.now())


def run_all_apps(settings: Settings, app_db: AppDatabase) -> None:
    """Continuous rendering loop. Renders due apps in parallel across available cores."""
    from concurrent.futures import ThreadPoolExecutor
    import os

    _check_pixlet()
    ensure_dirs()

    max_workers = min(os.cpu_count() or 2, 4)
    logger.info("Renderer starting with %d workers", max_workers)

    app_db.mark_all_stale()
    logger.info("Marked all apps stale — will re-render on first pass")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while True:
            apps = [a for a in app_db.list_apps() if a.enabled]
            if not apps:
                logger.warning("No enabled apps found, waiting...")
                sleep(MAX_TIME_BETWEEN_UPDATES.total_seconds())
                continue

            # Find all apps that are due for rendering
            due = [a for a in apps if _is_due(a)]

            if not due:
                # Sleep until the next app is due
                def next_update_time(app: AppConfig) -> datetime:
                    if app.last_updated is None:
                        return datetime.now()
                    return app.last_updated + app.refresh_interval

                next_app = min(apps, key=next_update_time)
                wait = (next_update_time(next_app) - datetime.now()).total_seconds()
                wait = min(max(wait, 0.5), MAX_TIME_BETWEEN_UPDATES.total_seconds())
                sleep(wait)
                continue

            # Sort by priority (high first), then by staleness (most overdue first)
            due.sort(key=lambda a: (-a.priority, a.last_updated or datetime.min))

            logger.info("Rendering %d due apps: %s", len(due), [a.name for a in due])

            # Submit all due apps to the thread pool
            futures = {
                pool.submit(_render_one, a.name, settings, app_db): a.name
                for a in due
            }

            # Wait for all to complete
            for future in futures:
                future.result()  # propagates exceptions if any

            # Brief pause before next check
            sleep(1)


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


COMMUNITY_RENDER_HEIGHT = 32  # Tidbyt/tronbyt community apps target 64x32


def _center_on_canvas(webp_path: Path, canvas_width: int, canvas_height: int) -> None:
    """Center a half-height render onto the full canvas, in place.

    Handles both static and animated WebP files.
    """
    with Image.open(webp_path) as img:
        if getattr(img, "is_animated", False):
            from PIL import ImageSequence
            frames = []
            durations = []
            for frame in ImageSequence.Iterator(img):
                canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
                f = frame.convert("RGBA")
                y_offset = (canvas_height - f.height) // 2
                canvas.paste(f, (0, y_offset))
                frames.append(canvas)
                durations.append(frame.info.get("duration", 100))
            if frames:
                frames[0].save(
                    webp_path, "WEBP", save_all=True, append_images=frames[1:],
                    duration=durations, loop=0,
                )
        else:
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 255))
            f = img.convert("RGBA")
            y_offset = (canvas_height - f.height) // 2
            canvas.paste(f, (0, y_offset))
            canvas.save(webp_path, "WEBP")


def _run_pixlet(app: AppConfig, settings: Settings, large: bool = False, star_override: Path | None = None) -> None:
    """Shell out to pixlet to render a Starlark app to .webp.

    Copies the .star file to a temp dir first as a workaround for a pixlet bug:
    https://discuss.tidbyt.com/t/strange-behavior-with-pixlet/6525

    Community apps (source="community") render at 64x32 then get centered on the
    full 64x64 canvas.
    """
    app_star = star_override or star_path(app.name)
    is_community = app.source == "community"

    # Community apps render at native Tidbyt height (32), then get centered
    render_height = COMMUNITY_RENDER_HEIGHT if is_community else settings.render_height

    with tempfile.TemporaryDirectory() as tmp:
        # If the .star lives in a subdirectory (community app with assets),
        # copy the entire directory so pixlet can resolve relative loads
        if app_star.parent.name != APPS_DIR.name:
            tmp_app_dir = Path(tmp) / app_star.parent.name
            shutil.copytree(app_star.parent, tmp_app_dir)
            tmp_star = str(tmp_app_dir / app_star.name)
        else:
            tmp_star = shutil.copy(app_star, tmp)

        if large:
            out = output_path_large(app.name)
        else:
            out = output_path(app.name)

        cmd = [
            "pixlet", "render", str(tmp_star),
            "-o", str(out),
            "-w", str(settings.render_width),
            "-t", str(render_height),
        ]
        if large:
            cmd.extend(["-m", str(settings.magnification)])

        for key, value in app.pixlet_config.items():
            cmd.append(f"{key}={value}")

        logger.debug("[%s] pixlet: %s", app.name, " ".join(cmd))
        proc = subprocess.run(cmd, env=os.environ, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.error("[%s] pixlet failed (rc=%d): %s", app.name, proc.returncode, proc.stderr)
            # Extract the useful part of stderr (last line of traceback usually has the error)
            stderr_lines = [l.strip() for l in proc.stderr.strip().splitlines() if l.strip()]
            detail = stderr_lines[-1] if stderr_lines else "unknown error"
            raise RuntimeError(f"[{app.name}] {detail}")

        # Center community apps on the full canvas
        if is_community and out.exists():
            if large:
                canvas_w = settings.render_width * settings.magnification
                canvas_h = settings.render_height * settings.magnification
            else:
                canvas_w = settings.render_width
                canvas_h = settings.render_height
            _center_on_canvas(out, canvas_w, canvas_h)


def _run_python_app(app: AppConfig, settings: Settings) -> None:
    """Run a Python applet that generates its own output.

    The Python file must define a render(settings, config, output, output_large) function.
    """
    mod_path = python_app_path(app.name)
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"phoenix.apps.{app.name}", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"[{app.name}] Could not load {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    render_fn = getattr(mod, "render", None)
    if render_fn is None:
        raise RuntimeError(f"[{app.name}] {mod_path} has no render() function")

    render_fn(
        settings=settings,
        config=app.pixlet_config,
        output=output_path(app.name),
        output_large=output_path_large(app.name),
    )

    # No output = app chose to skip (e.g., no data to display)
    if not output_path(app.name).exists():
        logger.info("[%s] render() produced no output (conditional skip)", app.name)


def _copy_static_app(app: AppConfig, settings: Settings) -> None:
    """Copy a static image (webp, gif, png) to the outputs directory, with magnified version."""
    src = static_app_path(app.name)
    if src is None:
        raise RuntimeError(f"[{app.name}] No static image found")

    out = output_path(app.name)
    out_large = output_path_large(app.name)

    # Convert/copy to webp at native size
    with Image.open(src) as img:
        # For animated images, copy as-is
        if getattr(img, "is_animated", False):
            shutil.copy(src, out)
            # Create magnified version
            frames = []
            durations = []
            for frame in __import__("PIL.ImageSequence", fromlist=["Iterator"]).Iterator(img):
                resized = frame.convert("RGBA").resize(
                    (settings.render_width * settings.magnification,
                     settings.render_height * settings.magnification),
                    Image.Resampling.NEAREST,
                )
                frames.append(resized)
                durations.append(frame.info.get("duration", 100))
            if frames:
                frames[0].save(
                    out_large, "WEBP", save_all=True, append_images=frames[1:],
                    duration=durations, loop=0,
                )
        else:
            # Static image
            rgb = img.convert("RGBA")
            small = rgb.resize((settings.render_width, settings.render_height), Image.Resampling.LANCZOS)
            small.save(out, "WEBP")
            large = rgb.resize(
                (settings.render_width * settings.magnification,
                 settings.render_height * settings.magnification),
                Image.Resampling.NEAREST,
            )
            large.save(out_large, "WEBP")
