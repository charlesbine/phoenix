load("render.star", "render")
load("http.star", "http")
load("encoding/base64.star", "base64")
load("cache.star", "cache")

LOCAL_SERVER = "http://127.0.0.1:8000"
ENDPOINT = "spotify_now_playing.json"

def main():
    endpoint = LOCAL_SERVER + "/" + ENDPOINT
    rep = http.get(endpoint)
    if rep.status_code != 200:
        fail("Request to %s failed with %d", endpoint, rep.status_code)

    json = rep.json()
    # TODO: check if now playing
    # TODO: once conditional eval is implemented, skip from rotation if not playing

    title = json["item"]["name"]
    artists = json["item"]["artists"]
    artists_string = ", ".join([artist["name"] for artist in artists])
    album_art_url = json["item"]["album"]["images"][-1]["url"]
    album_art = http.get(album_art_url).body()
    album_name = json["item"]["album"]["name"]

    return render.Root(
        render.Padding(
            pad=2,
            child=render.Box(
                render.Column(
                    # expanded = True,
                    # main_align = "space_evenly",
                    # cross_align = "center",
                    children = [
                        render.Image(src=album_art, width=32, height=32),
                        render.Marquee(width=64, align="start", child=render.Text(title, color="#1DB954")),
                        render.Marquee(width=64, align="start", child=render.Text(album_name)),
                        render.Marquee(width=64, align="start", child=render.Text(artists_string)),
                    ],
                ),
            ),
        ),
    )
