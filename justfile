host := "lyra"
remote_dir := "/home/charles/phoenix"

# Deploy latest code to Lyra and restart services
deploy:
    ssh {{host}} "cd {{remote_dir}} && git pull && sudo systemctl restart phoenix-dashboard phoenix-renderer phoenix-display"

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

# Run locally (dev mode)
dev:
    PHOENIX_PLATFORM=web mprocs

# Run locally with serial display
dev-serial:
    PHOENIX_PLATFORM=serial PHOENIX_SERIAL_PORT=/dev/cu.usbmodem101 mprocs
