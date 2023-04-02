import asyncio
import datetime
from pathlib import Path
import subprocess
import time

from loguru import logger

from app_db import get_app_by_name, upsert, read_all_apps


DEBUG = True


def run_app(name: str):
    """Render the output of the app called `name`."""
    start_time = time.perf_counter()
    logger.info(f"[{name}] running app")

    app = get_app_by_name(name)

    if not app.enabled:
        logger.debug(f"Skipping disabled app {app.name}")

    if not app.filename.exists():
        raise ValueError(f"File {app.filename} does not exist.")

    # TODO: pass args: eg "timezone=UTC" for clock
    args = ["pixlet", "render", str(app.filename), "-o", str(app.output_filename)]
    subprocess.run(args, check=True)
    if DEBUG:
        args = [
            "pixlet",
            "render",
            str(app.filename),
            "-o",
            str(app.output_filename_large),
            "-m",
            "5",
        ]
        subprocess.run(args, check=True)

    # update the last update time
    upsert(name, last_updated=datetime.datetime.now())
    update_time_elapsed = time.perf_counter() - start_time
    wait_time_remaining = app.refresh_interval.total_seconds() - update_time_elapsed
    logger.debug(
        f"[{app.name}] Waiting {wait_time_remaining:.1f} seconds "
        f"(of {app.refresh_interval}) before next update."
    )


def call_and_loop(loop, app_name: str, refresh_delay: int):
    run_app(app_name)
    loop.call_later(refresh_delay, call_and_loop, loop, app_name, refresh_delay)


def run_all_apps_sync():
    loop = asyncio.new_event_loop()

    for app in read_all_apps():
        refresh_interval_seconds = app.refresh_interval.total_seconds()
        loop.call_soon(call_and_loop, loop, app.name, refresh_interval_seconds)

    loop.run_forever()


if __name__ == "__main__":
    run_all_apps_sync()
