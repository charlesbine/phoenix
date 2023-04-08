load("render.star", "render")
load("http.star", "http")
load("encoding/base64.star", "base64")
load("cache.star", "cache")

LOCAL_SERVER = "http://127.0.0.1:8000"
ENDPOINT = "pixel_planet.json"

def main():
    endpoint = LOCAL_SERVER + "/" + ENDPOINT
    rep = http.get(endpoint)
    if rep.status_code != 200:
        fail("Request to %s failed with %d", endpoint, rep.status_code)

    json = rep.json()
    # TODO: check if now playing
    # TODO: once conditional eval is implemented, skip from rotation if not playing

    image = json["image"]

    return render.Root(
        render.Image(src=base64.decode(image), width=64, height=64)
    )
