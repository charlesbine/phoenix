"""Preprocessor discovery. Convention: any module here with a run() function is a preprocessor."""

import importlib
import logging
from collections.abc import Callable

from phoenix.models import PreprocessorResult
from phoenix.settings import Settings

logger = logging.getLogger(__name__)


def get_preprocessor(name: str) -> Callable[[Settings], PreprocessorResult] | None:
    """Import preprocessor module by app name. Returns its run() function, or None."""
    try:
        mod = importlib.import_module(f"phoenix.preprocessors.{name}")
        fn = getattr(mod, "run", None)
        if fn is None:
            return None
        return fn
    except ImportError:
        return None
    except Exception:
        logger.exception("Failed to import preprocessor '%s'", name)
        return None
