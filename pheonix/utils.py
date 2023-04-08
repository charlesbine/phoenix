from pathlib import Path


def output_dir() -> Path:
    """ Where the webp output of the starlark apps live """
    return Path(__file__).parent / "outputs"


def apps_dir() -> Path:
    """ Where the starlark apps live """
    return Path(__file__).parent / "apps"


def preprocessors_dir() -> Path:
    """ Where the optional python preprocessors live """
    return Path(__file__).parent / "preprocessors"


def data_dir() -> Path:
    """ Where the data files live. These are the output of the python job
    and will be read by the webserver to be served to the starlark jobs
    """
    return Path(__file__).parent / "data"


def get_downloaded_app_names() -> list[str]:
    """ Get the names of all the downloaded starlark apps """
    return [p.stem for p in apps_dir().glob("*.star")]