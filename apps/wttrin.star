load("render.star", "render")
load("http.star", "http")
load("cache.star", "cache")

API_ENDPOINT = "https://wttr.in/nyc?m0qFAT"

def main():
    weather_cached = cache.get("btc_rate")
    if weather_cached != None:
        print("Hit! Displaying cached data.")
        weather_text = weather_cached
    else:
        print("Miss! Calling wttr.in API.")
        rep = http.get(API_ENDPOINT)
        if rep.status_code != 200:
            fail("wttr.in request failed with status %d", rep.status_code)
        weather_text = rep.body()
        print(weather_text)
        cache.set("wttrin_weather", weather_text, ttl_seconds = 240)
    
    weather_lines = weather_text.splitlines()
    longest_line = max([len(line) for line in weather_lines])
    weather_lines = [ljust(line, longest_line) for line in weather_lines]
    weather_lines[3] += " "
    weather_lines[4] += "  "

    # for line in weather_lines:
    #     print(len(line))
    # print(weather_lines)

    return render.Root(
        child = render.Column(
            children = [
                render.Marquee(width=64, align="start", child=render.Text(
                    line,
                    font="5x8"))
                for line in weather_lines
            ],
        ),
    )


def ljust(string, length, fill = " "):
    fill = fill[0]
    if len(string) > length:
        return string
    return string + (length - len(string)) * fill