import datetime
from itertools import cycle
import random
import socket
import sys
import time
from typing import Optional

from loguru import logger
from PIL import Image, ImageSequence

from pheonix.app_db import read_all_apps, AppConfig, get_app_by_name
from pheonix.config import get_config
from pheonix.webapp.helpers import display_animated_image


IS_RASP = socket.gethostname() == "raspberrypi"

if IS_RASP:
    import sys

    sys.path.append("/usr/local/lib/python3.9/dist-packages/")

    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    # Configuration for the matrix
    options = RGBMatrixOptions()
    options.rows = 64  # 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    # 'regular'  # If you have an Adafruit HAT: 'adafruit-hat'
    options.hardware_mapping = "adafruit-hat"

    matrix = RGBMatrix(options=options)

else:
    # TODO: drop superuser privileges here if applicable
    import streamlit as st


# TODO: move to a config toml
ANIMATION_DELAY = 0.5
IMAGE_REFRESH_PERIOD = 10
#: number of seconds to wait before next update loop if all apps are stale
ALL_APPS_STALE_WAIT_TIME = 1


class DisplayManager:
    def __init__(self, debug_display_element=None):
        self.debug_display_element = debug_display_element

    @property
    def debug(self):
        return self.debug_display_element is not None

    def run_display(self):
        while True:
            apps = read_all_apps()
            active_apps = [app for app in apps if app.enabled and app.active]

            if len(active_apps) == 0:
                logger.error("No active apps found.")
                # TODO: display a default clock or something
                raise RuntimeError("no active apps found")

            if all(app.is_stale() for app in active_apps):
                # all apps are stale, so we wait for a bit to avoid an infinite loop
                logger.warning(f"All apps are stale, waiting for {ALL_APPS_STALE_WAIT_TIME}s")
                if IS_RASP:
                    matrix.Clear()
                time.sleep(ALL_APPS_STALE_WAIT_TIME)
                # we continue to refresh the apps
                continue

            config = get_config()
            logger.debug(f"Got config: {config}")
            logger.debug(f"Active enabled apps: {[app.name for app in active_apps]}")

            if config.layout_mode == "cycle":
                self.display_apps_in_cycle(active_apps, config.cycle_interval)
            elif config.layout_mode == "random":
                self.display_apps_in_random_order(active_apps, config.cycle_interval)
            elif config.layout_mode == "single":
                if len(active_apps) > 1:
                    logger.warning("More than one app is active, but display mode is single")
                self.display_app(active_apps[0], config.cycle_interval)
            else:
                raise ValueError(f"Unknown display mode {config.layout_mode}")

    def display_app(self, app: AppConfig, duration: int):
        """Display an app for `duration` seconds."""

        app = get_app_by_name(app.name)

        image_path = app.output_filename if not self.debug else app.output_filename_large

        if not app.output_filename.exists():
            logger.error(f"Output file {app.output_filename} does not exist")
            return

        if app.is_stale():
            logger.warning(f"App {app.name} is stale. Last updated {app.last_updated}. Skipping.")
            return

        logger.info(f"Displaying {app.name} for {duration} seconds, {image_path=}")

        if self.debug:
            display_animated_image(image_path, self.debug_display_element)
            time.sleep(duration)
            return

        with Image.open(image_path) as image:
            display_image(image, duration)

    def display_apps_in_cycle(self, apps: list[AppConfig], each_duration: int):
        """
        Display apps in a cycle, one at a time. Displays each one for
        `each_duration` seconds.
        """
        for app in apps:
            logger.debug(f"Displaying {app.name} for {each_duration} seconds")
            self.display_app(app, each_duration)

    def display_apps_in_random_order(self, apps: list[AppConfig], each_duration: int):
        """
        Display apps in a random order, one at a time. Displays each one for
        `each_duration` seconds.
        """
        apps_shuffled = apps.copy()
        random.shuffle(apps_shuffled)
        for app in apps_shuffled:
            self.display_app(app, each_duration)


## lower level funcs


def display_image(image, duration: int):
    is_still = len(ImageSequence.all_frames(image)) == 1

    if is_still:
        still(image, duration=duration)
    else:
        animate(image, duration=duration)


def animate(image, delay=None, duration: Optional[int] = None):
    start = end = time.perf_counter()

    # prerocessing the animation
    canvases = []
    durations = []
    for frame in ImageSequence.Iterator(image):
        canvas = matrix.CreateFrameCanvas()
        # maybe:
        # frame.thumnail(matrix.width, matrix.height, Image.ANTIALIAS)
        canvas.SetImage(frame.convert("RGB"))
        canvases.append(canvas)
        durations.append(frame.info["duration"] / 1000 if delay is None else delay)

    # can close the image now that we've processed the frames
    # to save some memory
    image.close()

    while end - start < duration:
        for canvas, cur_delay in zip(canvases, durations):
            canvas = matrix.SwapOnVSync(canvas)
            time.sleep(cur_delay)
            # when we get newer version with this PR
            # https://github.com/hzeller/rpi-rgb-led-matrix/pull/1447/commits
            # canvas = matrix.SwapOnVSync(canvas, framerate_fraction=10)

        # we put this outside the for to let the full animation play before ending it
        end = time.perf_counter()


def still(image, duration=IMAGE_REFRESH_PERIOD):
    """delay in seconds"""
    # Make image fit our screen.
    # image.thumbnail((matrix.width, matrix.height), Image.ANTIALIAS)
    matrix.Clear()
    matrix.CreateFrameCanvas().SetImage(image.convert("RGB"))
    matrix.SetImage(image.convert("RGB"))
    time.sleep(duration)


if __name__ == "__main__":
    print("Press CTRL-C to stop.")
    try:
        dm = DisplayManager()
        dm.run_display()
    except KeyboardInterrupt:
        sys.exit(0)
