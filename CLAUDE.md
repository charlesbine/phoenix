# Phoenix

Smart LED matrix display manager — Raspberry Pi renders apps, Matrix Portal M4 drives a 64x64 P2 HUB75 panel via DMA.

## Vision

Phoenix will be open-sourced. The goal is to build on the good ideas from Pixlet/Tidbyt but support HUB75 panels more generally, starting with 64x64 as the default. Keep this in mind when making design decisions — prefer clean abstractions, avoid hardcoding assumptions that only apply to our specific setup, and write code that others could pick up and run on their own hardware.

## Community Apps

Community apps come from **metaember/phoenix-apps** (https://github.com/metaember/phoenix-apps), our fork of tronbyt/apps (itself a fork of the now-dead tidbyt/community). Periodically merge upstream from tronbyt/apps for new apps and fixes. Community apps are Starlark (.star) targeting 64x32 — the renderer renders them at half height and centers on 64x64.

## Architecture

- **Renderer** (`phoenix render`): Renders apps via pixlet (Starlark) or direct Python, outputs .webp
- **Display** (`phoenix display`): Picks apps, streams RGB888 frames to M4 over USB serial
- **Dashboard** (`phoenix dashboard`): FastAPI JSON API + built Vue SPA on port 7002
- **M4 Firmware**: Dumb frame receiver, Protomatter DMA, gamma correction

## App Types

- `.star` (Starlark via pixlet) — community-compatible
- `.py` (Python with Pillow) — full Python capabilities
- Static images (.webp, .gif, .png)
- Dashboard panels (dynamic data visualization)
