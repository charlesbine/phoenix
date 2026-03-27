# Phoenix

A smart LED matrix display manager that drives a 64x64 HUB75 panel via an Adafruit Matrix Portal M4, powered by a Raspberry Pi.

<img src="phoenix/static/phoenix-logo.png" width="128" alt="Phoenix">

## Architecture

```
Pi (renderer + dashboard)  --USB serial-->  Matrix Portal M4 (DMA)  --HUB75-->  64x64 Panel
```

The Pi handles all rendering, scheduling, and the web dashboard. The M4 is a dumb frame receiver — it gets raw RGB bytes over USB serial and drives the panel via Protomatter DMA at ~200Hz. Zero tearing, zero jitter.

## Features

- **Dashboard panel builder** — create no-code displays from the web UI. Pick a layout (big number, key/value, marquee, multi stat, sparkline), point at a data source (HTTP JSON, MQTT, Home Assistant), and it renders automatically.
- **MQTT notifications** — publish to `phoenix/notify` and it interrupts the display within 100ms.
- **Home Assistant integration** — auto-discovers as a dimmable light in HA. Brightness slider, app switching, layout mode — all from HA dashboards and automations.
- **Starlark apps** — compatible with the Tidbyt/Pixlet ecosystem. Run community apps or write your own.
- **Python apps** — for anything that doesn't fit Starlark. Direct Pillow rendering, no limitations.
- **Playlist scheduling** — time-based playlists with day-of-week rules. Clock at night, stats during work hours.
- **Priority cycling** — important apps show more often (2x, 3x, 4x weighting).
- **HTTP cache proxy** — transparent caching with stale-on-failure fallback. External APIs going down won't break your display.

## Quick start

### On the Pi

```bash
# Install deps
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://github.com/tidbyt/pixlet/releases/download/v0.34.0/pixlet_0.34.0_linux_arm64.tar.gz \
  | sudo tar -xz -C /usr/local/bin pixlet

# Clone and configure
git clone https://github.com/metaember/phoenix.git
cd phoenix
cp .env.example .env  # edit with your settings

# Install and start
uv sync
bash deploy/install.sh
```

Dashboard at `http://<pi-ip>:7002`

### Development (Mac)

```bash
uv sync
just dev          # web backend + mprocs
just dev-serial   # with M4 connected
```

### Deployment

```bash
just deploy       # git pull + restart on Pi
just status       # check services
just logs         # live tail logs
just render-times # see what's slow
```

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

PHOENIX_MQTT_BROKER=mqtt.example.com
PHOENIX_MQTT_PORT=8883
PHOENIX_MQTT_TLS=true
PHOENIX_MQTT_USERNAME=user
PHOENIX_MQTT_PASSWORD=pass

PHOENIX_HA_URL=http://homeassistant.local:8123
PHOENIX_HA_TOKEN=your-long-lived-token
```

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
