"""
For modifying the config via a tinydb database.

The config will store information on what layout mode to use.
"""

import json
from pathlib import Path
import pydantic
from typing import ClassVar

from loguru import logger
from tinydb import TinyDB
from tinydb.table import Document


DB_DIR = Path(__file__).parent / "config_db.json"
DB = TinyDB(str(DB_DIR))


class Config(pydantic.BaseModel):
    SUPPORTED_LAYOUT_MODES: ClassVar[list[str]] = ["cycle", "single"]
    layout_mode: str = "cycle"

    # cycle layout params
    #: how long to wait between switching to the next app (in seconds)
    cycle_interval: int = 10

    # single layout params

    class Config:
        validate_assignment = True

    @pydantic.validator("layout_mode")
    def val_layout_mode(cls, layout_mode):
        if layout_mode not in cls.SUPPORTED_LAYOUT_MODES:
            raise ValueError(
                f"Unsupported layout mode: {layout_mode}. Are supported: "
                f"{cls.SUPPORTED_LAYOUT_MODES}")
        return layout_mode



def get_config() -> Config:
    raw_config = DB.get(doc_id=0)
    if raw_config is None:
        logger.warning("No config found in database, using default.")
        config = Config()
        set_config(config)
    else:
        config = Config(**raw_config)
    return config


def set_config(config: Config):
    DB.upsert(Document(json.loads(config.json()), doc_id=0))
