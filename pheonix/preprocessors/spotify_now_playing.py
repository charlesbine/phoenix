from app_db import get_app_by_name

from sptools import sptools


APPLET_NAME = "spotify_now_playing"


def main():
    """ Get the currently playing song from spotify and save it to a json file """
    app = get_app_by_name(APPLET_NAME)
    song = sptools.main("now_playing", json_path=app.data_file, overwrite=True)
    return song


if __name__ == "__main__":
    main()