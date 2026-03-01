load("render.star", "render")
load("http.star", "http")
load("math.star", "math")


LOCAL_SERVER = "http://127.0.0.1:7002/data"
ENDPOINT = "system_load.json"

def main():
    endpoint = LOCAL_SERVER + "/" + ENDPOINT
    rep = http.get(endpoint)
    if rep.status_code != 200:
        fail("Request to %s failed with %d", endpoint, rep.status_code)

    json = rep.json()

    # shape of json data
    # data = {
    #     "timestamp": now,
    #     "temperature": temperature,
    #     "cpu_load": {"1min": load1, "5min": load5, "15min": load15},
    #     "memory": {"total_MB": mem_total, "available_MB": mem_available},
    #     "disk": {"total_MB": disk_total, "free_MB": disk_free},
    #     "uptime": uptime,
    #     "throttled": throttled,
    # }

    # Define key-value pairs and colors
    KEY_COLOR = "#5BCEFA"  # Light blue color for keys

    # Format temperature data
    temp_key = "Temp:"
    temp_value = format_float(json["temperature"]) + "°C"

    # Format CPU load data
    load_key = "Ld:"
    load_value = format_float(json["cpu_load"]["1min"]) + " " + format_float(json["cpu_load"]["5min"]) + " " + format_float(json["cpu_load"]["15min"])

    # Format RAM usage data
    available_mb = json["memory"]["available_MB"]
    total_mb = json["memory"]["total_MB"]
    used_mb = total_mb - available_mb
    if used_mb == 0:
        ram_percentage = 0
    elif total_mb == 0:
        ram_percentage = "N/A"
    else:
        ram_percentage = int((used_mb / total_mb) * 100)

    ram_key = "RAM:"
    ram_value = str(ram_percentage) + "%"

    # Format uptime data
    uptime_key = "Up:"
    uptime_value = json["uptime"]

    # Format throttled data
    throttled_key = "Throt:"
    throttled_value = json["throttled"]

    return render.Root(
        render.Padding(
            pad=2,
            child=render.Box(
                render.Column(
                    expanded = True,
                    main_align = "space_evenly",
                    cross_align = "start",
                    children = [
                        render.Marquee(
                            width=64,
                            align="start",
                            child=render.Row(
                                children=[
                                    render.Text(temp_key, color=KEY_COLOR),
                                    render.Text(" " + temp_value),
                                ],
                            )
                        ),
                        render.Marquee(
                            width=64,
                            align="start",
                            child=render.Row(
                                children=[
                                    render.Text(load_key, color=KEY_COLOR),
                                    render.Text(" " + load_value),
                                ],
                            )
                        ),
                        render.Marquee(
                            width=64,
                            align="start",
                            child=render.Row(
                                children=[
                                    render.Text(ram_key, color=KEY_COLOR),
                                    render.Text(" " + ram_value),
                                ],
                            )
                        ),
                        render.Marquee(
                            width=64,
                            align="start",
                            child=render.Row(
                                children=[
                                    render.Text(uptime_key, color=KEY_COLOR),
                                    render.Text(" " + uptime_value),
                                ],
                            )
                        ),
                        render.Marquee(
                            width=64,
                            align="start",
                            child=render.Row(
                                children=[
                                    render.Text(throttled_key, color=KEY_COLOR),
                                    render.Text(" " + throttled_value),
                                ],
                            )
                        ),
                    ],
                ),
            ),
        ),
    )



def format_float(value, decimals=1):
    if type(value) not in (type(1), type(1.1)):
        return value

    v = str(int(math.round(value * math.pow(10, decimals))))
    v = (v[0:-decimals] + "." + v[-decimals:])
    return v