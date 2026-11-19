#!/usr/bin/env bash
set -euo pipefail

echo "Installing Phoenix services..."

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHOENIX_USER="${PHOENIX_USER:-$(id -un)}"
PHOENIX_DIR="${PHOENIX_DIR:-$REPO_DIR}"

if ! command -v bun >/dev/null 2>&1 && [ -x "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
fi

if ! command -v bun >/dev/null 2>&1; then
    echo "Missing bun. Install it first: curl -fsSL https://bun.sh/install | bash" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1 && [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi

PHOENIX_UV="${PHOENIX_UV:-$(command -v uv || true)}"
if [ -z "$PHOENIX_UV" ]; then
    echo "Missing uv. Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

cd "$PHOENIX_DIR"

echo "Installing Python dependencies..."
"$PHOENIX_UV" sync

echo "Building dashboard frontend..."
(
    cd frontend
    bun install --frozen-lockfile
    bun run build
)

echo "Rendering systemd unit files (user=$PHOENIX_USER, dir=$PHOENIX_DIR)..."
escape_sed() { printf '%s' "$1" | sed 's/[&|\\]/\\&/g'; }
ESC_USER="$(escape_sed "$PHOENIX_USER")"
ESC_DIR="$(escape_sed "$PHOENIX_DIR")"
ESC_UV="$(escape_sed "$PHOENIX_UV")"

for unit in deploy/phoenix-*.service; do
    name="$(basename "$unit")"
    sed \
        -e "s|__PHOENIX_USER__|${ESC_USER}|g" \
        -e "s|__PHOENIX_DIR__|${ESC_DIR}|g" \
        -e "s|__PHOENIX_UV__|${ESC_UV}|g" \
        "$unit" | sudo tee "/etc/systemd/system/$name" >/dev/null
done

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
