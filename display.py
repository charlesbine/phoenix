from itertools import cycle
import sys
import time

from PIL import Image, ImageSequence
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from app_db import read_all_apps


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
        for app in active_apps:
            image = app.output_filename
            load_and_display(image)


def animate(image, delay=None):
    while True:
        for frame in ImageSequence.Iterator(image):
            delay = frame.info["duration"] / 1000 if delay is None else delay
            still(frame, delay=delay)


def still(image, delay=IMAGE_REFRESH_PERIOD):
    """delay in seconds"""
    # Make image fit our screen.
    # image.thumbnail((matrix.width, matrix.height), Image.ANTIALIAS)
    matrix.Clear()
    matrix.SetImage(image.convert("RGB"))
    time.sleep(delay)


def display(image):
    is_still = len(ImageSequence.all_frames(image)) == 1

    if is_still:
        still(image)
    else:
        animate(image)


def load_and_display(path):
    image = Image.open(path)
    display(image)


if __name__ == "__main__":
    print("Press CTRL-C to stop.")
    try:
        run_display()
    except KeyboardInterrupt:
        sys.exit(0)
