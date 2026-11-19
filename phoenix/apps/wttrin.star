load("render.star", "render")
load("http.star", "http")
load("schema.star", "schema")

CACHE_PROXY = "http://127.0.0.1:7002/proxy"
DEFAULT_LOCATION = "San Francisco"
CACHE_TTL = 900  # 15 minutes — weather doesn't change that fast

def main(config):
    location = (config.get("location") or DEFAULT_LOCATION).strip().replace(" ", "+")
    units = config.get("units") or "m"
    unit_flag = "u" if units == "u" else "m"
    api_endpoint = "https://wttr.in/{}?{}0qFAT".format(location, unit_flag)

    rep = http.get(CACHE_PROXY, params={"url": api_endpoint, "ttl": str(CACHE_TTL)})
    if rep.status_code != 200:
        fail("wttr.in request failed with status %d", rep.status_code)
    weather_text = rep.body()
    weather_lines = weather_text.splitlines()

    # Normalize and pad each line to ensure consistent visual width
    display_width = max([len(normalize_special_chars(line)) for line in weather_lines])  # Set a fixed display width    print("display width: ", display_width)
    normalized_lines = []

    for line in weather_lines:
        # Pad to fixed width with spaces
        padded_line = ljust(line, display_width)
        normalized_lines.append(padded_line)

    normalized_lines = remove_trailing_spaces(normalized_lines)

    return render.Root(
        child = render.Column(
            children = [
                render.Marquee(
                    width=64,
                    align="start",
                    child=render.Text(line, font="5x8")  # Try a different font
                )
                for line in normalized_lines
            ],
        ),
    )

def normalize_special_chars(text):
    """Replace special characters with visually consistent alternatives.
    These render as a single character, but count as more than one character
    when evaluated in line length. So we perform this replacement on the text
    that will be used to compute the justification sizes, but not on the text
    that will actually get displayed.
    """
    replacements = {
        "↑": "^",
        "↓": "v",
        "→": ">",
        "←": "<",
        "↗": ">",
        "↘": "v",
        "↖": "^",
        "↙": "<",
        "°": "*",
        "’": "'",
        "―": "-",
        # Add more replacements as needed
    }

    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    return text


def ljust(string, length, fill = " "):
    fill = fill[0]
    normalized_string = normalize_special_chars(string)
    if len(normalized_string) > length:
        return string
    return string + (length - len(normalized_string)) * fill


def remove_trailing_spaces(lines):
    """Remove trailing spaces from all lines while maintaining consistent width.

    This function:
    1. Finds the minimum number of trailing spaces across all lines
    2. Removes exactly that many spaces from each line
    3. Returns the trimmed lines with consistent width
    """
    if not lines:
        return []

    # Count trailing spaces in each line
    trailing_spaces = []
    for line in lines:
        count = 0
        for char in reversed(line.elems()):
            if char != " ":
                break
            count += 1
        trailing_spaces.append(count)

    # Find minimum number of trailing spaces
    min_spaces = min(trailing_spaces)

    # Remove exactly min_spaces from each line
    trimmed_lines = []
    for line in lines:
        if min_spaces > 0:
            trimmed_lines.append(line[:-min_spaces])
        else:
            trimmed_lines.append(line)

    return trimmed_lines


def get_schema():
    return schema.Schema(
        version = "1",
        fields = [
            schema.Text(
                id = "location",
                name = "Location",
                desc = "City name, airport code, or postal code for wttr.in",
                icon = "locationDot",
                default = DEFAULT_LOCATION,
            ),
            schema.Dropdown(
                id = "units",
                name = "Units",
                desc = "Metric (°C, km/h) or USCS (°F, mph)",
                icon = "temperatureHalf",
                default = "m",
                options = [
                    schema.Option(display = "Metric (°C)", value = "m"),
                    schema.Option(display = "Imperial (°F)", value = "u"),
                ],
            ),
        ],
    )
