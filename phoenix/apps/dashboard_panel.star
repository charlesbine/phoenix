"""Generic dashboard panel — renders different layouts based on JSON config.

Reads its config from /data/dashboard_panel_{instance_id}.json written by the preprocessor.
The JSON contains: layout, title, values, colors, etc.
"""

load("render.star", "render")
load("http.star", "http")
load("encoding/json.star", "json")
load("math.star", "math")

LOCAL_SERVER = "http://127.0.0.1:7002/data"

def main(config):
    instance_id = config.get("instance_id", "default")
    endpoint = LOCAL_SERVER + "/dashboard_panel_" + instance_id + ".json"
    rep = http.get(endpoint)
    if rep.status_code != 200:
        return render_error("No data")

    data = rep.json()
    layout = data.get("layout", "big_number")

    if layout == "big_number":
        return render_big_number(data)
    elif layout == "key_value":
        return render_key_value(data)
    elif layout == "marquee":
        return render_marquee(data)
    elif layout == "multi_stat":
        return render_multi_stat(data)
    else:
        return render_error("Unknown layout: " + layout)


def render_error(msg):
    return render.Root(
        child = render.Box(
            child = render.WrappedText(
                content = msg,
                font = "tom-thumb",
                color = "#FF4444",
                align = "center",
            ),
        ),
    )


def render_big_number(data):
    """Large value with label and optional unit/trend."""
    value = str(data.get("value", "—"))
    label = data.get("title", "")
    unit = data.get("unit", "")
    color = data.get("color", "#FFFFFF")
    label_color = data.get("label_color", "#8899AA")

    display_value = value + unit

    children = []

    if label:
        children.append(
            render.Text(
                content = label,
                font = "tom-thumb",
                color = label_color,
            )
        )
        children.append(render.Box(width = 64, height = 2))

    children.append(
        render.Text(
            content = display_value,
            font = "6x13",
            color = color,
        )
    )

    return render.Root(
        child = render.Box(
            child = render.Column(
                expanded = True,
                main_align = "center",
                cross_align = "center",
                children = children,
            ),
        ),
    )


def render_key_value(data):
    """Rows of label: value pairs."""
    items = data.get("items", [])
    title = data.get("title", "")
    key_color = data.get("key_color", "#5BCEFA")
    value_color = data.get("value_color", "#FFFFFF")
    title_color = data.get("title_color", "#8899AA")

    children = []

    if title:
        children.append(
            render.Padding(
                pad = (0, 0, 0, 1),
                child = render.Text(
                    content = title,
                    font = "tom-thumb",
                    color = title_color,
                ),
            )
        )

    for item in items[:5]:  # Max 5 rows
        key = str(item.get("key", ""))
        val = str(item.get("value", ""))
        children.append(
            render.Marquee(
                width = 64,
                align = "start",
                child = render.Row(
                    children = [
                        render.Text(key + " ", color = key_color, font = "tom-thumb"),
                        render.Text(val, color = value_color, font = "tom-thumb"),
                    ],
                ),
            )
        )

    return render.Root(
        child = render.Padding(
            pad = 1,
            child = render.Column(
                expanded = True,
                main_align = "space_evenly",
                cross_align = "start",
                children = children,
            ),
        ),
    )


def render_marquee(data):
    """Scrolling text — good for headlines or messages."""
    text = data.get("text", "")
    title = data.get("title", "")
    color = data.get("color", "#FFFFFF")
    title_color = data.get("title_color", "#8899AA")

    children = []

    if title:
        children.append(
            render.Padding(
                pad = (0, 0, 0, 2),
                child = render.Text(
                    content = title,
                    font = "tom-thumb",
                    color = title_color,
                ),
            )
        )

    children.append(
        render.Marquee(
            width = 64,
            child = render.Text(
                content = text,
                font = "6x13",
                color = color,
            ),
        )
    )

    return render.Root(
        child = render.Padding(
            pad = 2,
            child = render.Column(
                expanded = True,
                main_align = "center",
                cross_align = "center",
                children = children,
            ),
        ),
    )


def render_multi_stat(data):
    """2-4 values in a grid with labels."""
    stats = data.get("stats", [])
    title = data.get("title", "")
    title_color = data.get("title_color", "#8899AA")
    label_color = data.get("label_color", "#8899AA")
    value_color = data.get("value_color", "#FFFFFF")

    def stat_cell(stat):
        val = str(stat.get("value", ""))
        label = stat.get("label", "")
        stat_color = stat.get("color", value_color)
        return render.Column(
            cross_align = "center",
            children = [
                render.Text(val, font = "6x13", color = stat_color),
                render.Text(label, font = "tom-thumb", color = label_color),
            ],
        )

    n = min(len(stats), 4)
    children = []

    if title:
        children.append(
            render.Text(content = title, font = "tom-thumb", color = title_color)
        )

    if n <= 2:
        # Single row
        row = [stat_cell(s) for s in stats[:2]]
        children.append(
            render.Row(expanded = True, main_align = "space_evenly", children = row)
        )
    else:
        # 2x2 grid — top row and bottom row
        top = [stat_cell(s) for s in stats[:2]]
        bot = [stat_cell(s) for s in stats[2:4]]
        children.append(
            render.Row(expanded = True, main_align = "space_evenly", children = top)
        )
        children.append(
            render.Row(expanded = True, main_align = "space_evenly", children = bot)
        )

    return render.Root(
        child = render.Padding(
            pad = (2, 1, 2, 1),
            child = render.Column(
                expanded = True,
                main_align = "space_evenly",
                cross_align = "center",
                children = children,
            ),
        ),
    )
