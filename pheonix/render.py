import datetime
import importlib
import os
import subprocess
import time
import tempfile
import shutil
import pathlib
from typing import Optional

from loguru import logger

from pheonix.app_db import get_app_by_name, upsert, read_all_apps, AppConfig
from pheonix.types import AppStatus


#: should we also generate a 5x magnified version ? It is used for display in the UI's
RUN_LARGE = True

#: render size for the pixlet apps
#: note that some apps have internal config that causes the layout to be smaller
RENDER_WIDTH = 64
RENDER_HEIGHT = 64

# this controls how often we check for new apps to render
# useful if we have a bunch of slow updating apps and want to guarantee that
# adding a new quick updating app will not be queued for a long time
MAX_TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=30)


def run_app(name: str):
    """Render the output of the app called `name`."""
    app = get_app_by_name(name)

    # TODO: wrap all this in a try/except and determine what to do if an app fails
    # either at the python or pixlet stages. Probably the right thing to do is
    # to do some retries with exponential backoff, and then give up and disable

    if not app.enabled:
        logger.debug(f"[{app.name}] Skipping disabled app {app.name}")
        return

    if not app.filename.exists():
        raise ValueError(f"File {app.filename} does not exist.")

    if app.uses_preprocessor:
        logger.info(f"[{app.name}] Running preprocessor {app.python_filename}")
        try:
            module = importlib.import_module(f"pheonix.preprocessors.{app.python_filename.stem}")
            data = module.main()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error(f"[{app.name}] Preprocessor raised an exception: {e}")
            logger.exception(e)
            data = None

        if data is None or data is AppStatus.SKIP:
            # TODO: change this to only if returned AppStatus.SKIP
            logger.warning(f"[{app.name}] Preprocessor returned None or AppStatus.SKIP, skipping.")

            # remove the data files so the display doesn't try to use them
            if app.output_filename.exists():
                logger.info(f"[{app.name}] Removing old data file {app.output_filename}")
                app.output_filename.unlink()
            if app.output_filename_large.exists():
                logger.info(f"[{app.name}] Removing old data file {app.output_filename_large}")
                app.output_filename_large.unlink()
            return
        # TODO: support other AppStatus values here

    logger.info(f"[{name}] running applet")
    run_app_generation(app)
    if RUN_LARGE:
        run_app_generation(app, large=True)

    # update the last update time
    upsert(name, last_updated=datetime.datetime.now())


def run_app_generation(app: AppConfig, large: bool = False):
    """Run the command to generate the app.

    This will copy the app file temporarily to a temp file, workaround for a pixlet bug
    https://discuss.tidbyt.com/t/strange-behavior-with-pixlet/6525
    """

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = pathlib.Path(temp_dir) / app.filename.name
        shutil.copy(app.filename, temp_file)

        command = get_app_generation_command(app, large, str(temp_file))
        logger.debug(f"[{app.name}] Running command: {' '.join(command)}")
        subprocess.run(command, check=True, env=os.environ)


def get_app_generation_command(app: AppConfig, large: bool = False, app_file: Optional[str] = None):
    """Return the command to generate the app."""

    if app_file is None:
        app_file = str(app.filename)

    command = ["pixlet", "render", app_file]
    if large:
        command.extend(["-o", str(app.output_filename_large), "-m", "5"])
    else:
        command.extend(["-o", str(app.output_filename)])

    for key, value in app.pixlet_config_kwargs.items():
        command.extend([f"{key}={value}"])

    command.extend(["-w", str(RENDER_WIDTH), "-t", str(RENDER_HEIGHT)])

    # TODO: add the command line args from the app config eg "timezone=UTC" for clock
    # these should be read from a dict or somethign in the database?
    return command


def run_all_apps():
    """Run all apps. The app database is read at every iteration, so apps can be
    added or removed while this is running."""
    while True:
        all_apps = read_all_apps()
        all_enabled = [app for app in all_apps if app.enabled]

        def expected_next_update_time(app: AppConfig) -> datetime.datetime:
            """When should this app be updated next? If the app has never been updated,
            then we assume it should be updated now."""
            if app.last_updated is None:
                return datetime.datetime.now()
            return app.last_updated + app.refresh_interval

        next_app_to_run = min(all_enabled, key=expected_next_update_time)
        now = datetime.datetime.now()
        time_to_next_update = expected_next_update_time(next_app_to_run) - now

        if time_to_next_update > MAX_TIME_BETWEEN_UPDATES:
            # if the next app is too far in the future, then we'll just wait for the
            # max time between updates
            time_to_next_update = MAX_TIME_BETWEEN_UPDATES
            logger.debug(
                "Nothing to update in the next "
                f"{MAX_TIME_BETWEEN_UPDATES.total_seconds()} seconds, "
                "will check again then."
            )
            time.sleep(time_to_next_update.total_seconds())
            continue

        # set any negative number to 0
        clipped_time_to_next_update = max(time_to_next_update.total_seconds(), 0)

        logger.debug(
            f"Next app to run is {next_app_to_run.name} in "
            f"{time_to_next_update.total_seconds():.1f} seconds"
        )

        time.sleep(clipped_time_to_next_update)
        run_app(next_app_to_run.name)
