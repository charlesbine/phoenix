from itertools import cycle
import random
import sys
import time
from typing import Optional

from loguru import logger
from PIL import Image, ImageSequence

from app_db import read_all_apps, AppConfig
from config import get_config


DEBUG = True


if not DEBUG:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions

    # Configuration for the matrix
    options = RGBMatrixOptions()
    options.rows = 64  # 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.hardware_mapping = (
        "adafruit-hat"  # 'regular'  # If you have an Adafruit HAT: 'adafruit-hat'
    )

    matrix = RGBMatrix(options=options)


# TODO: move to a config toml
ANIMATION_DELAY = 0.5
IMAGE_REFRESH_PERIOD = 10


def run_display():
    while True:
        apps = read_all_apps()
        active_apps = [app for app in apps if app.enabled and app.active]

        if len(active_apps) == 0:
            logger.error("No active apps found.")
            # TODO: display a default clock or something
            raise RuntimeError("no active apps found")

        config = get_config()

        if config.layout_mode == "cycle":
            display_apps_in_cycle(active_apps, config.cycle_interval)
        elif config.layout_mode == "random":
            display_apps_in_random_order(active_apps, config.cycle_interval)
        elif config.layout_mode == "single":
            if len(active_apps) > 1:
                logger.waring("More than one app is active, but display mode is single")
        else:
            raise ValueError(f"Unknown display mode {config.layout_mode}")
        

def display_app(app: AppConfig, duration: int):
    """ Display an app for `duration` seconds."""
    image = app.output_filename
    load_and_display(image, duration)


def display_apps_in_cycle(apps: list[AppConfig], each_duration: int):
    """Display apps in a cycle, one at a time. Displays each one for `each_duration` seconds."""
    for app in cycle(apps):
        display_app(app, each_duration)


def display_apps_in_random_order(apps: list[AppConfig], each_duration: int):
    """Display apps in a random order, one at a time. Displays each one for `each_duration` seconds."""
    while True:
        app = random.choice(apps)
        display_app(app, each_duration)


## lower level funcs

def load_and_display(path, duration: int):
    with Image.open(path) as image:
        if DEBUG:
            display_image_debug(image, duration)
        else:
            display_image(image, duration)


def display_image_debug(image, duration: int):
    image.show()
    time.sleep(duration)


def display_image(image, duration: int):
    is_still = len(ImageSequence.all_frames(image)) == 1

    if is_still:
        still(image, duration=duration)
    else:
        animate(image, duration=duration)


def animate(image, delay=None, duration: Optional[int] = None):
    start = end = time.perf_counter()
    while end - start < duration:
        for frame in ImageSequence.Iterator(image):
            delay = frame.info["duration"] / 1000 if delay is None else delay
            still(frame, duration=delay)

        # we put this outside the for to let the full animation play before ending it
        end = time.perf_counter()


def still(image, duration=IMAGE_REFRESH_PERIOD):
    """delay in seconds"""
    # Make image fit our screen.
    # image.thumbnail((matrix.width, matrix.height), Image.ANTIALIAS)
    matrix.Clear()
    matrix.SetImage(image.convert("RGB"))
    time.sleep(duration)




if __name__ == "__main__":
    print("Press CTRL-C to stop.")
    try:
        run_display()
    except KeyboardInterrupt:
        sys.exit(0)
