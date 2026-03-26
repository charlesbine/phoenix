# Phoenix TODO

## Done
- [x] Dashboard builder (4 layouts, HTTP/MQTT/HA sources, auth, transforms)
- [x] MQTT support (persistent client, topic subscriptions, message store)
- [x] Notifications (MQTT + HTTP, display interrupt within 100ms)
- [x] HA sensor data (REST API data source for panels)
- [x] Priority cycling (weighted rotation)
- [x] Conditional rendering (packages app pattern)
- [x] Fullscreen display page (/display)

## Deploy
- [ ] Flash Lyra (Pi 3) with Ubuntu 24.04 LTS
- [ ] Install uv + pixlet, clone repo, set up systemd services
- [ ] Wire M4 via USB, verify serial display works

## Features
- [ ] Time-based scheduling — show certain apps at certain times (clock at night, weather in morning)
- [ ] HA MQTT discovery — expose Phoenix as a device in HA (brightness, current app, app switching)
- [ ] Sparkline layout template — mini line chart for time series (daily MRR, temperature history)
- [ ] Transitions — fade to black between apps instead of hard cut
- [ ] Systemd service files for Pi deployment (replace mprocs)

## Nice to have
- [ ] WebSocket for live dashboard updates instead of 15s polling
- [ ] Multi-panel rotation — group panels into a single app slot that sub-cycles faster
- [ ] Image/GIF URL panel type — fetch and display an image from a URL
- [ ] ntfy bridge — MQTT → ntfy for phone push notifications alongside display
