"""Select a random planet GIF from assets and base64 encode it for Starlark."""

import base64
import json
from random import choice

from phoenix.models import AppStatus, PreprocessorResult
from phoenix.paths import ASSETS_DIR, data_path
from phoenix.settings import Settings

PLANET_DIR = ASSETS_DIR / "pixel_planet"


def run(settings: Settings) -> PreprocessorResult:
    gifs = list(PLANET_DIR.glob("*.gif"))
    if not gifs:
        return PreprocessorResult(data=None, status=AppStatus.SKIP)

    selected = choice(gifs)
    encoded = base64.b64encode(selected.read_bytes()).decode()
    data_path("pixel_planet").write_text(json.dumps({"image": encoded}))
    return PreprocessorResult(data=selected.stem)
