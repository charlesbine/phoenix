import asyncio
import datetime
from pathlib import Path
import subprocess
import time

from loguru import logger

from app_db import get_app_by_name, upsert, read_all_apps, AppConfig


#: should we also generate a 5x magnified version ? It is used for display in the UI's
RUN_LARGE = True

RENDER_WIDTH = 64
RENDER_HEIGHT = 64


def run_app(name: str):
    """Render the output of the app called `name`."""
    start_time = time.perf_counter()
    app = get_app_by_name(name)

    if not app.enabled:
        logger.debug(f"[{app.name}] Skipping disabled app {app.name}")
        return
    
    logger.info(f"[{name}] running app")
    
    if not app.filename.exists():
        raise ValueError(f"File {app.filename} does not exist.")

    if app.uses_preprocessor:
        logger.info(f"[{app.name}] Running preprocessor {app.python_filename}")
        subprocess.run(["python", str(app.python_filename)], check=True)

    subprocess.run(get_app_generation_command(app), check=True)
    if RUN_LARGE:
        subprocess.run(get_app_generation_command(app, large=True), check=True)

    # update the last update time
    upsert(name, last_updated=datetime.datetime.now())
    update_time_elapsed = time.perf_counter() - start_time
    wait_time_remaining = app.refresh_interval.total_seconds() - update_time_elapsed
    logger.debug(
        f"[{app.name}] Waiting {wait_time_remaining:.1f} seconds "
        f"(of {app.refresh_interval}) before next update."
    )


def get_app_generation_command(app: AppConfig, large: bool = False):
    """Return the command to generate the app."""
    command = ["pixlet", "render", str(app.filename)] 
    if large:
        command.extend(["-o", str(app.output_filename_large), "-m", "5"])
    else:
        command.extend(["-o", str(app.output_filename)])
    
    # TODO: add the siza args
    command.extend(["-w", str(RENDER_WIDTH), "-t", str(RENDER_HEIGHT)])

    # TODO: add the command line args from the app config eg "timezone=UTC" for clock

    return command


def call_and_loop(loop, app_name: str, refresh_delay: int):
    run_app(app_name)
    loop.call_later(refresh_delay, call_and_loop, loop, app_name, refresh_delay)


def run_all_apps_sync():
    loop = asyncio.new_event_loop()

    for app in read_all_apps():
        refresh_interval_seconds = app.refresh_interval.total_seconds()
        loop.call_soon(call_and_loop, loop, app.name, refresh_interval_seconds)

    # TODO: add a handler to check for new apps and remove old apps
    # old apps might not need to get removed since they can be disabled though

    loop.run_forever()


if __name__ == "__main__":
    run_all_apps_sync()
