# Phoenix TODO

## Done
- [x] M4 display driver + serial streaming with gamma correction
- [x] HTTP cache proxy with stale-on-failure fallback
- [x] Pluggable renderer (Starlark, Python, static images)
- [x] Preact dashboard SPA (config, drag reorder, previews, schema-aware editor)
- [x] Dashboard panel builder (5 layouts: big number, key/value, marquee, multi stat, sparkline)
- [x] Data sources: HTTP JSON, MQTT topics, Home Assistant entities
- [x] Auth support (Bearer, API key, Basic) + value transforms
- [x] MQTT notifications with display interrupt (<100ms)
- [x] HA MQTT discovery (Phoenix as dimmable light + select entities)
- [x] Priority cycling (weighted rotation) + conditional rendering
- [x] Playlist scheduling (time-based, day-of-week)
- [x] Refresh presets (realtime/frequent/ambient)
- [x] Parallel rendering across all CPU cores
- [x] Systemd deployment with nice priorities
- [x] Health endpoint (/healthz, /api/health)
- [x] File logging with render timing
- [x] Fullscreen display page (/display)
- [x] Deployed on Lyra (Pi 3) with external panel PSU

## Features
- [ ] Transitions — fade to black between apps instead of hard cut
- [ ] M4 temperature telemetry — read SAMD51 internal temp, report back to Pi
- [ ] WebSocket for live dashboard updates instead of 15s polling

## Nice to have
- [ ] Multi-panel rotation — group panels into a single app slot that sub-cycles faster
- [ ] Image/GIF URL panel type — fetch and display an image from a URL
- [ ] ntfy bridge — MQTT to ntfy for phone push alongside display
- [ ] Auto-brightness via ambient light sensor on M4 I2C
