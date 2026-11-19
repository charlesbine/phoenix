# Matrix Portal M4 Firmware

Phoenix’s Matrix Portal M4 firmware receives sRGB RGB888 frames over USB serial and drives
a 64×64, 1/32-scan HUB75E panel with Protomatter.

The default LUT decodes sRGB to linear intensity for each channel. The firmware
quantizes directly to six bits per channel and writes the scan buffers, preserving
all six planes for red, green, and blue. The existing frame brightness byte
controls the active-low OE pulse in each plane. TCC0/WO[0] on D16 (PB12) ends that
pulse independently of the CPU. Protomatter’s TC4 still advances the scan and
the row latch stays blanked. At brightness zero no OE pulses are emitted.

The default uses equal curves for all three channels and needs no panel
measurements. If a calibrated profile is available, serial command `0x08`
accepts 768 bytes in R, G, B table order (256 entries each). Command `0x01`
still accepts a shared 256-byte table. The entries are linear intensities from
0 to 255, rounded to the nearest native level. `0x03` restores sRGB. LUTs apply
to the next frame and reset on reboot. The status gamma byte is zero because
these profiles do not have a single power-law exponent. Frame format and
brightness range are unchanged.

## Flash with arduino-cli

```bash
# Install arduino-cli (if you don't have it)
brew install arduino-cli

# One-time setup: add Adafruit board support
arduino-cli core update-index --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
arduino-cli core install adafruit:samd --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json

# Install required libraries
arduino-cli lib install "Adafruit Protomatter@1.7.1" "Adafruit GFX Library" "Adafruit LIS3DH" "Adafruit NeoPixel"

# Compile
bash build.sh /tmp/phoenix-m4

# Upload (M4 must be connected via USB)
arduino-cli upload --fqbn adafruit:samd:adafruit_matrixportal_m4 --input-dir /tmp/phoenix-m4 -p /dev/ttyACM0 .
```

If the M4 doesn't show up as `/dev/ttyACM0`, double-tap the reset button to enter the bootloader — it'll appear as a USB drive and a different serial port.

The build script patches a temporary copy of Protomatter 1.7.1. The patch adds
the OE pulse call at the point where the next plane is latched and ready.
Other projects can continue using the stock Arduino library.

Run the color and timing math checks from this directory with a host C++ compiler.

```bash
c++ -std=c++11 -Wall -Wextra -Werror ../tests/panel_color_test.cpp -o /tmp/panel-color-test
/tmp/panel-color-test
```
