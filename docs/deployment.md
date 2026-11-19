# Deployment Guide

Phoenix can run as a single all-in-one host or split across a central server and one or more display nodes. Because `PHOENIX_SERVICES` selects which processes run (`dashboard`, `render`, `display`), the same codebase and container image cover every topology.

## 1. All-in-One with Docker Compose

Best when one Linux host or mini-PC sits next to your LED panel (or drives WLED panels over Wi-Fi).

```bash
cp .env.example .env
# Edit .env — set PHOENIX_PLATFORM=wled (or serial) and any optional integrations
docker compose up -d --build
```

The default [`docker-compose.yml`](../docker-compose.yml) starts all three services (`dashboard`, `render`, `display`), exposes the Ember-CRT web dashboard on port `7002`, and passes through `/dev/ttyACM0` (Matrix Portal M4) and `/dev/snd` (optional USB mic for the audio visualizer).

If you only use WLED panels (e.g., Apollo M-1) and have no USB serial device or mic attached, remove the `devices:` entries from `docker-compose.yml` and set `PHOENIX_PLATFORM=wled`.

## 2. Native systemd (Raspberry Pi / Linux)

On low-RAM boards (such as a 1 GB Raspberry Pi 3), running Phoenix natively under systemd avoids Docker daemon overhead and makes USB serial + ALSA audio setup straightforward.

### Prerequisites

- Python 3.11+ and [`uv`](https://docs.astral.sh/uv/)
- [`bun`](https://bun.sh/) (for building the Vue dashboard bundle)
- [`pixlet`](https://github.com/tidbyt/pixlet/releases) on `$PATH`

### Install services

```bash
git clone https://github.com/charlesbine/phoenix.git
cd phoenix
cp .env.example .env
# Edit .env for your platform and integrations

./deploy/install.sh
```

`deploy/install.sh` syncs Python dependencies, builds the frontend bundle, renders the unit templates in `deploy/phoenix-*.service` with your current username, repo path, and `uv` binary path (overridable via `PHOENIX_USER`, `PHOENIX_DIR`, `PHOENIX_UV`), and enables three systemd units:

- `phoenix-dashboard` — FastAPI server, Vue UI, cache proxy, MQTT client
- `phoenix-renderer` — Starlark/Python applet render loop (`Nice=10`)
- `phoenix-display` — Frame streaming to serial/WLED/matrix panels (`Nice=-5`)

### Optional: USB Microphone for Audio Visualizer

```bash
sudo apt install -y libportaudio2 alsa-utils
sudo usermod -aG audio "$USER"   # log out and back in after
uv sync --extra audio

# List detected PortAudio input devices and pin one in .env if needed:
uv run python -c "from phoenix.audio.source import list_input_devices as l; print(l())"
# Set PHOENIX_AUDIO_DEVICE=USB in .env, then:
sudo systemctl restart phoenix-display
```

On 1 GB Pis, set `PHOENIX_RENDER_WORKERS=1` in `.env` and consider enabling `zram-tools` so concurrent renders cannot exhaust memory.

## 3. Split Deployment (Controller Server + Paired Serial Player)

If your Raspberry Pi only has 1 GB RAM — or you want a single dashboard managing both WLED panels and a USB-attached Matrix Portal M4 — split the stack:

```
Home Server (Docker)                           USB Display Host (native systemd)
[dashboard + render]  ── private HTTPS ──▶     [phoenix node: HTTPS receiver + display] ── USB ──▶ M4 ──▶ Panel
```

### Step A: Start the controller ("brain")

```bash
docker compose -f deploy/split/docker-compose.yml up -d --build
```

The Compose file binds the dashboard to `127.0.0.1:7002` and persists the SQLite database (`PHOENIX_DB_PATH=/var/lib/phoenix/phoenix.db`), data directory, and rendered WebPs in named volumes. Put the dashboard behind your authenticated reverse proxy (Traefik, Caddy, Nginx) on the same Docker network, targeting port `7002`, and remove the loopback port mapping if you don't need local access.

### Step B: Generate a shared token and TLS certificate

Generate a random token (at least 32 characters) and copy it with `0600` permissions to both hosts:

```bash
openssl rand -hex 32 > phoenix_node_token
chmod 600 phoenix_node_token
```

Generate a self-signed certificate with an IP SAN matching the display host's private LAN IP (e.g., `192.168.1.50`):

```bash
openssl req -x509 -newkey ed25519 -nodes -days 3650 \
  -keyout node.key -out node.crt \
  -subj "/CN=phoenix-node" \
  -addext "subjectAltName=IP:192.168.1.50"
chmod 600 node.key
```

Keep `node.key` only on the display host, and copy `node.crt` to the controller host as `PHOENIX_NODE_CA_FILE`.

### Step C: Register the serial panel & configure both hosts

1. Open the dashboard → **Devices**, and add a panel with backend `serial` (for example, ID `desk`).
2. On the **display host**, set in `.env`:

| Variable | Example / Purpose |
|---|---|
| `PHOENIX_NODE_DEVICE` | `desk` (must match the dashboard device ID) |
| `PHOENIX_NODE_TOKEN_FILE` | `/etc/phoenix/node_token` (owner-only `0600`) |
| `PHOENIX_NODE_BIND` | `192.168.1.50` (player's private LAN IP) |
| `PHOENIX_NODE_PORT` | `7443` (HTTPS listener port) |
| `PHOENIX_NODE_PEER` | `192.168.1.10` (controller's LAN source IP) |
| `PHOENIX_NODE_TLS_CERT` | `/etc/phoenix/node.crt` |
| `PHOENIX_NODE_TLS_KEY` | `/etc/phoenix/node.key` (owner-only `0600`) |
| `PHOENIX_SERIAL_PORT` | `/dev/ttyACM0` |

Run `uv run phoenix node` under systemd on the display host. It serves the private HTTPS receiver and independently drives the serial panel from its local disk cache.

3. On the **controller**, set:

| Variable | Example / Purpose |
|---|---|
| `PHOENIX_NODE_DEVICE` | `desk` |
| `PHOENIX_NODE_URL` | `https://192.168.1.50:7443` |
| `PHOENIX_NODE_TOKEN_FILE` | `/run/secrets/phoenix_node_token` |
| `PHOENIX_NODE_CA_FILE` | `/run/secrets/phoenix_node_ca.crt` |

### Resilience & Security Notes

- The receiver accepts uploads only from `PHOENIX_NODE_PEER` presenting the Bearer token, and validates that every uploaded frame is a valid 64×64 WebP within size/frame limits.
- The display host persists its accepted rotation, Night Mode / brightness schedule, timezone/solar coordinates, and rendered WebPs on disk, so it continues playing uninterrupted across restarts and controller outages.
- When upgrading a split deployment, upgrade the display player before the controller.

## 4. Remote Maintenance via `just`

The root [`justfile`](../justfile) wraps common SSH deployment and inspection commands. Override the target host and directory via environment variables:

```bash
export PHOENIX_HOST=my-pi.local
export PHOENIX_REMOTE_DIR=/home/pi/phoenix

just deploy        # git pull, uv sync, build frontend, restart systemd units
just status        # systemctl status
just logs          # live journalctl tail
just render-times  # recent render durations
```
