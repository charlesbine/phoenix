import datetime
import json
from pathlib import Path
from typing import Optional

import pandas as pd
import pydantic
from tinydb import TinyDB, Query
import tomli

from utils import apps_dir, output_dir


DEFAULT_UPDATE_INTERVAL = datetime.timedelta(minutes=1)

DB_DIR = Path(__file__).parent / "db.json"
DB = TinyDB(str(DB_DIR))


class AppConfig(pydantic.BaseModel):
    # name of the app, should be unique
    name: str
    # how long to wait between consecutive renders
    refresh_interval: datetime.timedelta = DEFAULT_UPDATE_INTERVAL
    # last time it got rendered
    last_updated: Optional[datetime.datetime] = None
    # active means it should get displayed
    active: bool = True
    # enabled means it should be rendered
    enabled: bool = True

    @property
    def filename(self) -> Path:
        return apps_dir() / (self.name + ".star")

    @property
    def output_filename(self) -> Path:
        return output_dir() / (self.name + ".webp")

    @property
    def output_filename_large(self) -> Path:
        return output_dir() / (self.name + ".large.webp")

    @pydantic.validator("refresh_interval", pre=True)
    def val_refresh_interval(cls, refresh_interval):
        if isinstance(refresh_interval, str):
            return pd.Timedelta(refresh_interval).to_pytimedelta()
        elif isinstance(refresh_interval, datetime.time):
            date = datetime.date.today()
            return datetime.datetime.combine(
                date, refresh_interval
            ) - datetime.datetime.combine(date, datetime.time(0))
        return refresh_interval

    def save(self):
        pass


class Config(pydantic.BaseModel):
    apps: list[AppConfig]

    @pydantic.validator("apps")
    def check_names_unique(cls, apps):
        if len(set(app.name for app in apps)) < len(apps):
            raise ValueError("Cannot have duplicate names in app config.")
        return apps


def read_all_apps() -> list[AppConfig]:
    return Config(apps=DB.all()).apps


def get_app_by_name(name: str):
    App = Query()
    app = DB.get(App.name == name)
    if app is None:
        raise ValueError(f"No app found in db for name {name}")

    return AppConfig(**app)


def upsert(name: str, **kwargs):
    config = AppConfig(name=name, **kwargs)
    App = Query()
    app = DB.get(App.name == name)
    if app is None:
        # we get the defaults from the pydantic constructor
        DB.insert(json.loads(config.json()))
    else:
        app.update(kwargs)
        config = AppConfig(**app)
        DB.update(json.loads(config.json()), App.name == name)
