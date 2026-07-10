#!/bin/bash
set -e

echo "Installing Phoenix services..."

if ! command -v bun >/dev/null 2>&1 && [ -x "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
fi

if ! command -v bun >/dev/null 2>&1; then
    echo "Missing bun. Install it first: curl -fsSL https://bun.sh/install | bash"
    exit 1
fi

echo "Installing Python dependencies..."
uv sync

echo "Building dashboard frontend..."
(
    cd frontend
    bun install --frozen-lockfile
    bun run build
)

# Copy service files
sudo cp deploy/phoenix-*.service /etc/systemd/system/

# Copy .env to the working directory if it exists
if [ -f .env ]; then
    echo "Found .env — services will use it"
fi

# Reload and enable
sudo systemctl daemon-reload
sudo systemctl enable phoenix-dashboard phoenix-renderer phoenix-display

# Start
sudo systemctl start phoenix-dashboard
sleep 2
sudo systemctl start phoenix-renderer phoenix-display

echo ""
echo "Phoenix is running!"
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):7002"
echo ""
echo "Commands:"
echo "  sudo systemctl status phoenix-dashboard phoenix-renderer phoenix-display"
echo "  sudo journalctl -u phoenix-dashboard -f"
echo "  sudo systemctl restart phoenix-dashboard phoenix-renderer phoenix-display"
