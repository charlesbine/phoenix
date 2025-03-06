from pheonix.app_db import get_app_by_name
from pheonix.types import PreprocessorResult, AppStatus

from sptools import sptools


APPLET_NAME = "spotify_now_playing"


def main():
    """ Get the currently playing song from spotify and save it to a json file """
    app = get_app_by_name(APPLET_NAME)
    song = sptools.main("now_playing", json_path=app.data_file, overwrite=True)

    if song is None:
        return PreprocessorResult(None, AppStatus.SKIP)

    return PreprocessorResult(song, AppStatus.PRIORITIZE, priority=30)


if __name__ == "__main__":
    main()