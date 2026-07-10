host := "lyra"
remote_dir := "/home/charles/phoenix"

# Deploy latest code to Lyra and restart services
deploy:
    ssh {{host}} "export PATH=\"\$HOME/.bun/bin:\$PATH\" && cd {{remote_dir}} && git pull && uv sync && cd frontend && bun install --frozen-lockfile && bun run build && cd .. && sudo systemctl restart phoenix-dashboard phoenix-renderer phoenix-display"

# Check service status on Lyra
status:
    ssh {{host}} "sudo systemctl status phoenix-dashboard phoenix-renderer phoenix-display --no-pager"

# View live logs on Lyra
logs:
    ssh {{host}} "sudo journalctl -u phoenix-dashboard -u phoenix-renderer -u phoenix-display -f"

# View render timing stats
render-times:
    ssh {{host}} "grep 'Render complete' {{remote_dir}}/phoenix/logs/phoenix.log | tail -30"

# View recent log file
log-file lines="50":
    ssh {{host}} "tail -{{lines}} {{remote_dir}}/phoenix/logs/phoenix.log"

# Restart all services
restart:
    ssh {{host}} "sudo systemctl restart phoenix-dashboard phoenix-renderer phoenix-display"

# Stop all services
stop:
    ssh {{host}} "sudo systemctl stop phoenix-dashboard phoenix-renderer phoenix-display"

# Start all services
start:
    ssh {{host}} "sudo systemctl start phoenix-dashboard phoenix-renderer phoenix-display"

# SSH into Lyra
ssh:
    ssh {{host}}

# Flash M4 firmware (run locally, M4 must be connected to this machine)
flash-m4:
    arduino-cli compile --fqbn adafruit:samd:adafruit_matrixportal_m4 firmware/matrix_portal_m4
    arduino-cli upload --fqbn adafruit:samd:adafruit_matrixportal_m4 -p /dev/cu.usbmodem101 firmware/matrix_portal_m4

# Run the local dashboard stack
dev:
    @echo "Starting Phoenix backend on :7002 and Vue dashboard on :5173"
    PHOENIX_PLATFORM=web uv run phoenix dashboard & backend_pid=$!; trap 'kill "$backend_pid" 2>/dev/null' EXIT INT TERM; cd frontend && bun run dev -- --host 0.0.0.0

# Run the local FastAPI backend
dev-backend:
    PHOENIX_PLATFORM=web uv run phoenix dashboard

# Run the Vue dashboard dev server
dev-frontend:
    cd frontend && bun run dev -- --host 0.0.0.0

# Build the production dashboard bundle served by phoenix dashboard
build-frontend:
    cd frontend && bun run build

# Run local display services without the dashboard UI dev server
dev-display:
    PHOENIX_PLATFORM=web uv run phoenix render & render_pid=$!; trap 'kill "$render_pid" 2>/dev/null' EXIT INT TERM; PHOENIX_PLATFORM=web uv run phoenix display

# Run local display services with serial output
dev-display-serial:
    PHOENIX_PLATFORM=serial PHOENIX_SERIAL_PORT=/dev/cu.usbmodem101 uv run phoenix render & render_pid=$!; trap 'kill "$render_pid" 2>/dev/null' EXIT INT TERM; PHOENIX_PLATFORM=serial PHOENIX_SERIAL_PORT=/dev/cu.usbmodem101 uv run phoenix display

# Backwards-compatible serial runner name
dev-serial: dev-display-serial
