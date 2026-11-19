# Apollo M-1 & WLED Panels (Recommended Easy Path)

If you want a 64×64 Phoenix desk display with **zero soldering, zero firmware flashing, and no USB cable tethered to a Pi**, start with a WLED-compatible 64×64 HUB75 matrix such as the **[Apollo Automation M-1](https://apolloautomation.com/products/m-1-led-matrix)** (or any ESP32 HUB75 controller running WLED with 2D matrix support).

Phoenix streams full 64×64 RGB frames over your LAN using **DDP (Distributed Display Protocol)** on UDP port `4048` — committing each frame atomically with the `PUSH` flag to eliminate tearing — and controls panel brightness and power over WLED's HTTP JSON API (`/json/state`).

## What You Need

- **Panel:** Apollo M-1 (pre-assembled 64×64 RGB matrix + ESP32-S3 + enclosure + diffuser + USB-C power) or a custom ESP32 + 64×64 HUB75 panel flashed with WLED.
- **Host:** Any machine on the same LAN running Phoenix (Mac, Linux mini-PC, Raspberry Pi, or a home server running Docker). No direct cable to the panel is needed.

## Step 1: Set Up WLED on the Panel

1. Power on your Apollo M-1 and connect it to your Wi-Fi network (follow Apollo's onboarding flow or WLED's captive portal `WLED-AP`).
2. Assign a **DHCP reservation / static IP** for the panel in your router (for example, `192.168.1.100`). You can also use mDNS (`PHOENIX_WLED_IP=auto`), though a static IP is fastest and most reliable.
3. Open the WLED web UI (`http://192.168.1.100`) and verify:
   - **Config → 2D Configuration:** `2D Matrix` enabled, **64×64** dimensions, serpentine/orientation matching your physical mount.
   - **Config → Sync Interfaces → Realtime:** `Receive UDP realtime` enabled (DDP listens on UDP port `4048` by default).
   - **Config → LED Preferences:** Set a safe maximum current limit matching your power supply (e.g. `2500–3500 mA` for USB-C PD on Apollo M-1).

## Step 2: Connect Phoenix

### Option A: Add via the Dashboard (Recommended for Multi-Panel)

1. Start Phoenix (`docker compose up -d` or `just dev`).
2. Open the dashboard at `http://localhost:7002` and go to **Devices**.
3. Under **Add panel**, enter:
   - **ID:** `apollo` (or any slug like `desk`)
   - **Name:** `Apollo M-1`
   - **Backend:** `wled`
   - **Address:** `192.168.1.100` (your panel's LAN IP)
4. Click **Add panel**, switch to it in the top panel bar, and add apps from **Apps** or **Store**.

### Option B: Single-Panel `.env` Configuration

If this Phoenix instance drives a single WLED panel as its default `main` device:

```env
PHOENIX_PLATFORM=wled
PHOENIX_WLED_IP=192.168.1.100
```

To use automatic mDNS discovery instead of an IP address, install the optional `wled` extra and set `PHOENIX_WLED_IP=auto`:

```bash
uv sync --extra wled
```

## Quick Smoke Test via CLI

Before setting up a full rotation, test streaming a GIF or image straight to the panel:

```bash
uv run phoenix play path/to/animation.gif --ip 192.168.1.100
```

## Brightness, Night Mode & Multi-Panel

- **Brightness slider** on **Home** adjusts the WLED panel brightness immediately over HTTP (`/json/state`).
- **Night Mode & custom schedules** in **Devices → Brightness schedule** automatically dim the panel to 25% between sunset and sunrise and turn it off overnight (midnight–8 a.m. weekdays, 2–9 a.m. weekends — or your own custom schedule). Phoenix also periodically reconciles brightness and power state so the panel recovers cleanly after a controller restart.
- **Multiple panels:** Register as many WLED panels as you like in **Devices**. Each panel has its own rotation, layout mode (`cycle`, `random`, or `single`), brightness schedule, or can mirror another panel.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Panel stays on WLED's default orange effect | Confirm the host running `phoenix display` can reach UDP port `4048` on the panel's IP (same VLAN/subnet, no firewall blocking outbound UDP `4048`). |
| Image looks upside down or scrambled | Check **WLED → Config → 2D Configuration** panel dimensions (`64×64`), start corner, and orientation. |
| Panel flickers or browns out on white frames | Lower WLED's brightness cap or maximum current limiter under **Config → LED Preferences**, or use a dedicated 5V 3A+ USB-C power adapter. |
| `PHOENIX_WLED_IP=auto` can't find the panel | Ensure `uv sync --extra wled` is installed and mDNS (`_wled._tcp`) is allowed on your network (Docker bridge containers often block multicast — use a static IP in Docker). |
