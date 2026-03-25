# Matrix Portal M4 Firmware

Dumb frame receiver for Phoenix. Receives RGB888 frames over USB serial and displays them on a 64x64 HUB75 panel via Protomatter DMA.

## Flash with arduino-cli

```bash
# Install arduino-cli (if you don't have it)
brew install arduino-cli

# One-time setup: add Adafruit board support
arduino-cli core update-index --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
arduino-cli core install adafruit:samd --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json

# Install required libraries
arduino-cli lib install "Adafruit Protomatter" "Adafruit GFX Library"

# Compile
arduino-cli compile --fqbn adafruit:samd:adafruit_matrixportal_m4 .

# Upload (M4 must be connected via USB)
arduino-cli upload --fqbn adafruit:samd:adafruit_matrixportal_m4 -p /dev/ttyACM0 .
```

If the M4 doesn't show up as `/dev/ttyACM0`, double-tap the reset button to enter the bootloader — it'll appear as a USB drive and a different serial port.
