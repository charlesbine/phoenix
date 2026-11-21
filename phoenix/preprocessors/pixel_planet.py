"""Select a planet GIF — either pre-generated from assets or procedurally generated.

Pre-generated planet GIFs and the procedural planet re-implementation are based on
Deep-Fold's Pixel Planet Generator (MIT License):
https://deep-fold.itch.io/pixel-planet-generator
https://github.com/Deep-Fold/PixelPlanets
"""

import base64
import json
import random

from phoenix.models import PreprocessorResult
from phoenix.paths import ASSETS_DIR, data_path
from phoenix.procedural.pixel_planet import PLANET_TYPES, generate_planet_gif
from phoenix.settings import Settings

PLANET_DIR = ASSETS_DIR / "pixel_planet"

# Probability of generating a procedural planet vs picking a pre-made one
PROCEDURAL_CHANCE = 0.5


def run(settings: Settings) -> PreprocessorResult:
    use_procedural = random.random() < PROCEDURAL_CHANCE
    pre_made_gifs = list(PLANET_DIR.glob("*.gif"))

    if use_procedural or not pre_made_gifs:
        planet_type = random.choice(list(PLANET_TYPES.keys()))
        seed = random.randint(1, 99999)
        gif_bytes = generate_planet_gif(planet_type=planet_type, seed=seed)
        encoded = base64.b64encode(gif_bytes).decode()
        data_path("pixel_planet").write_text(json.dumps({"image": encoded}))
        return PreprocessorResult(data=f"procedural:{planet_type}:{seed}")

    selected = random.choice(pre_made_gifs)
    encoded = base64.b64encode(selected.read_bytes()).decode()
    data_path("pixel_planet").write_text(json.dumps({"image": encoded}))
    return PreprocessorResult(data=selected.stem)
