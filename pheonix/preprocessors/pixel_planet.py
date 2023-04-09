import base64
import json
from pathlib import Path
from random import choice

from pheonix import utils
from pheonix import app_db

APPLET_NAME = "pixel_planet"


def main():
    app = app_db.get_app_by_name(APPLET_NAME)
    planet_dir = utils.apps_dir() / APPLET_NAME
    selected_file = choice(list(planet_dir.glob("*.gif")))
    # code to base64 encode the selected file
    encoded = base64.b64encode(selected_file.read_bytes())    
    # code to save the encoded file to the data file
    app.data_file.write_text(json.dumps({"image": encoded.decode()}))
    return


if __name__ == "__main__":
    main()