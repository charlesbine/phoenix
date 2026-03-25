# Phoenix TODO

## Dashboard
- [ ] WebSocket for live dashboard updates instead of 15s polling (skip if large lift)

## Smart Home
- [ ] Home Assistant integration — expose brightness, current app, app switching as HA entities
- [ ] MQTT support — subscribe to feeds for sensor data, notifications, etc.
- [ ] HA sensor data ingestion — pull sensor readings for use in applets

## Scheduling & Notifications
- [ ] Time-based scheduling — show certain apps at certain times (clock at night, weather in morning)
- [ ] Notification support — temporarily interrupt cycle to show a notification (HA alert, timer, doorbell), then resume

## Content
- [ ] Dashboard builder — a flexible way to publish simple dashboards without code changes. Define a data source (HTTP endpoint, MQTT topic, HA entity), pick a layout template (key/value list, big number, sparkline, icon + text), and it renders automatically. No .star or .py file needed — just config in the DB/dashboard UI.
