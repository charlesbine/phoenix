load("render.star", "render")
load("http.star", "http")
load("encoding/base64.star", "base64")

LOCAL_SERVER = "http://127.0.0.1:7002/data"
ENDPOINT = "spotify.json"

def main():
    endpoint = LOCAL_SERVER + "/" + ENDPOINT
    rep = http.get(endpoint)
    if rep.status_code != 200:
        fail("Request to %s failed with %d", endpoint, rep.status_code)

    json = rep.json()
    if json == None:
        return render.Root(render.Text("Nothing playing"))

    title = json["track"]
    artist = json["artist"]
    album_art_url = json.get("album_art_url", "")

    children = []

    if album_art_url != "":
        album_art = http.get(album_art_url).body()
        children.append(render.Image(src=album_art, width=32, height=32))

    children.append(render.Marquee(width=64, align="start", child=render.Text(title, color="#1DB954")))
    children.append(render.Marquee(width=64, align="start", child=render.Text(artist)))

    return render.Root(
        render.Padding(
            pad=2,
            child=render.Box(
                render.Column(
                    children=children,
                ),
            ),
        ),
    )
