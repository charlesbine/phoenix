#!/usr/bin/env bash
set -euo pipefail

sketch_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
build_dir="${1:?Usage: bash build.sh <output-directory>}"
arduino_user_dir="$(arduino-cli config get directories.user)"
protomatter="$arduino_user_dir/libraries/Adafruit_Protomatter"

if ! grep -qx 'version=1.7.1' "$protomatter/library.properties" 2>/dev/null; then
    echo 'Install Adafruit Protomatter@1.7.1 before building Aurora firmware.' >&2
    exit 1
fi

staged="$(mktemp -d "${TMPDIR:-/tmp}/aurora-protomatter.XXXXXX")"
trap 'rm -rf "$staged"' EXIT
cp -R "$protomatter" "$staged/Adafruit_Protomatter"
patch --batch --forward --fuzz=0 -d "$staged/Adafruit_Protomatter" -p1 \
    < "$sketch_dir/protomatter-1.7.1-oe.patch"

arduino-cli compile --fqbn adafruit:samd:adafruit_matrixportal_m4 \
    --library "$staged/Adafruit_Protomatter" --build-path "$staged/build" \
    --output-dir "$build_dir" "$sketch_dir"
