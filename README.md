# Phoenix

A smart LED matrix display manager that drives a 64x64 HUB75 panel via an Adafruit Matrix Portal M4, powered by a Raspberry Pi.

<img src="phoenix/static/phoenix-logo.png" width="128" alt="Phoenix">

## Architecture

In an all-in-one installation the dashboard, renderer, and display player run
on the same machine. WLED panels receive DDP over the LAN. A Matrix Portal M4
receives RGB frames over USB and drives its HUB75 panel.

In a split installation the dashboard and renderer run on a server. A paired
serial player runs `phoenix node` on the machine connected to the M4. The
dashboard pushes settings and changed WebPs over private HTTPS. The player
caches the rotation and keeps playing on its own during a server outage.
The dashboard reports whether the player has accepted the update.

## Features

- **Dashboard panel builder** — create no-code displays from the web UI. Pick a layout (big number, key/value, marquee, multi stat, sparkline), point at a data source (HTTP JSON, MQTT, Home Assistant), and it renders automatically.
- **MQTT notifications** — publish to `phoenix/notify` and it interrupts the display within 100ms.
- **Home Assistant integration** — auto-discovers as a dimmable light in HA. Brightness slider, app switching, layout mode — all from HA dashboards and automations.
- **Starlark apps** — compatible with the Tidbyt/Pixlet ecosystem. Run community apps or write your own.
- **Python apps** — for anything that doesn't fit Starlark. Direct Pillow rendering, no limitations.
- **Playlist scheduling** — time-based playlists with day-of-week rules. Clock at night, stats during work hours.
- **Brightness scheduling** — daily brightness and power changes per WLED or serial panel, configured in Devices.
- **Quick app settings** — select an app on Home and open Settings under its preview. Save & render updates the shared app configuration and renders the preview. Apps has the custom key editor and app management.
- **Programming Excuses** — rotates a bundled list and learns new excuses from [programmerexcuses.com](http://programmerexcuses.com/) as it renders, at most once every 15 minutes. The site serves one random excuse per request. The local pool in `phoenix/data/programming_excuses_pool.json` works offline and grows over time.
- **Priority cycling** — important apps show more often (2x, 3x, 4x weighting).
- **HTTP cache proxy** — transparent caching with stale-on-failure fallback. External APIs going down won't break your display.

## Quick start

### On the Pi

```bash
# Install deps
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.sh/install | bash
curl -fsSL https://github.com/tidbyt/pixlet/releases/download/v0.34.0/pixlet_0.34.0_linux_arm64.tar.gz \
  | sudo tar -xz -C /usr/local/bin pixlet

# Clone and configure
git clone https://github.com/metaember/phoenix.git
cd phoenix
cp .env.example .env  # edit with your settings

# Install and start
bash deploy/install.sh
```

Dashboard at `http://<pi-ip>:7002`

### Development (Mac)

```bash
uv sync
cd frontend && bun install
just dev           # backend on :7002 + Vue dashboard on :5173
just dev-backend   # FastAPI API + production bundle server on :7002
just dev-frontend  # Vue dev server on :5173, proxies API to :7002
```

### Deployment — all-in-one (Pi)

```bash
just deploy       # git pull + sync deps + build Vue bundle + restart on Pi
just status       # check services
just logs         # live tail logs
just render-times # see what's slow
```

### Deployment — split server and serial player

See [Split deployment](deploy/europa/README.md) for the loopback-only Compose
example, private HTTPS pairing, and native serial player setup.

## Hardware

- **Raspberry Pi 3** (or newer) — runs the software
- **Adafruit Matrix Portal M4** — drives the panel via DMA
- **64x64 P2 HUB75 LED panel** — the display
- **5V PSU** — powers the panel directly (not through USB)
- **USB-A to USB-C cable** — Pi to M4 (data + M4 power only)

## Configuration

All settings via environment variables (`.env` file):

```env
PHOENIX_PLATFORM=serial
PHOENIX_SERIAL_PORT=/dev/ttyACM0

# Which services a process runs (space-separated): dashboard render display.
# All-in-one leaves this unset (runs all three); a brain sets "dashboard render".
PHOENIX_SERVICES="dashboard render display"
# Concurrent pixlet renders. 0 = auto (min(cores, 4)). Set 1 on a low-RAM Pi.
PHOENIX_RENDER_WORKERS=0
# Optional SQLite path. The parent directory must exist. Keep it out of /data.
# PHOENIX_DB_PATH=/var/lib/phoenix/phoenix.db

PHOENIX_MQTT_BROKER=mqtt.example.com
PHOENIX_MQTT_PORT=8883
PHOENIX_MQTT_TLS=true
PHOENIX_MQTT_USERNAME=user
PHOENIX_MQTT_PASSWORD=pass

PHOENIX_HA_URL=http://homeassistant.local:8123
PHOENIX_HA_TOKEN=your-long-lived-token
```

## Brightness and Night Mode

In **Devices**, choose a time zone once under **Global display settings**. A city's
latitude and longitude give Night Mode its local sunset and sunrise. Without a
location, it dims between 7 p.m. and 7 a.m. local time.

Night Mode is enabled by default for WLED and serial panels without a saved
schedule. The panel uses its brightness slider in daylight and 25% of that
level after dark. It powers off midnight–8 a.m. Monday through Friday and
2–9 a.m. on Saturday and Sunday mornings. One button turns Night Mode on or
off. Use **Custom schedule** for daily start times and brightness levels,
including 0 for off. Switching to Night Mode keeps your saved custom times.
Scheduled WLED panels periodically recover their configured brightness and
power state after a controller restart.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard UI |
| `GET /display` | Fullscreen display mirror |
| `GET /healthz` | Simple health check (200/503) |
| `GET /api/health` | Detailed diagnostics |
| `GET /api/apps` | List registered apps |
| `POST /api/notify` | Send a notification |
| `GET /api/panels` | List dashboard panels |
| `GET /api/settings/display` | Read the global time zone, solar location, and supported time zones |
| `PUT /api/settings/display` | Set the global `timezone`, `latitude`, and `longitude` |
| `PUT /api/devices/{id}/brightness-schedule` | Set `enabled`, `mode` (`night` or `custom`), and saved custom `steps` with `time` and `brightness` |
| `POST /api/panels` | Create a panel |
| `GET /proxy?url=...&ttl=300` | HTTP cache proxy |

## M4 Firmware

```bash
just flash-m4    # compile + upload (M4 must be connected locally)
```

Or manually:
```bash
cd firmware/matrix_portal_m4
arduino-cli compile --fqbn adafruit:samd:adafruit_matrixportal_m4 .
arduino-cli upload --fqbn adafruit:samd:adafruit_matrixportal_m4 -p /dev/cu.usbmodem101 .
```
