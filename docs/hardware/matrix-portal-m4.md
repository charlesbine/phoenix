# DIY 64×64 HUB75 + Adafruit Matrix Portal M4

For makers who want raw 64×64 HUB75 image quality, hardware-timed low-brightness dimming, and full control over the enclosure and diffuser, Phoenix supports an **Adafruit Matrix Portal M4** over USB serial.

The M4 acts as a dedicated DMA frame receiver: your host machine (a Raspberry Pi, Linux mini-PC, or Mac) renders applets and streams raw 64×64 RGB888 frames over USB, while the SAMD51 microcontroller drives the HUB75E panel via Protomatter DMA with zero flicker or tearing.

## Bill of Materials

| Part | Spec / Notes | Est. Cost |
|---|---|---|
| **64×64 RGB LED Matrix Panel** | P2, P2.5, or P3 pitch, **1/32 scan, HUB75E** (5 address lines `A–E`). P2 (~128×128 mm) or P2.5 (~160×160 mm) are ideal desk sizes. | $25–$45 |
| **Adafruit Matrix Portal M4** | SAMD51 (Cortex-M4) with onboard HUB75 header, USB-C, and STEMMA QT. *(Note: M4, not S3 — the TCC0 hardware OE driver targets SAMD51.)* | $25 |
| **5V 4A+ Power Supply** | Regulated 5V DC barrel or screw-terminal PSU dedicated to the panel. **Do not power a 64×64 panel solely from a Pi's USB port.** | $10–$15 |
| **Host computer** | Raspberry Pi 3/4/5/Zero 2 W, mini-PC, or Mac connected to the M4 over USB-C data cable. | $15–$55 |
| **Optional: Acrylic diffuser** | 2–3 mm smoked/black LED acrylic sheet (e.g. Chemcast Black LED Acrylic) dramatically improves contrast and blends individual LEDs. | $5–$10 |
| **Optional: USB microphone** | Any cheap USB mic plugged into the host unlocks the live 60 FPS audio visualizer (`bars`, `vu`, `spectrogram`). | $5–$10 |
| **Optional: SCD40 CO₂ sensor** | Adafruit SCD-40 / SCD-41 STEMMA QT breakout — automatically read by the M4 firmware and exposed in status telemetry. | $40 |

## Step 1: Bridge the Address-E Jumper on the Matrix Portal M4

64×64 1/32-scan panels require five row-address lines (`A`, `B`, `C`, `D`, **`E`**). On the back of the Matrix Portal M4, find the **Address E** solder jumper pads (`8` — middle — `16`):

- Most modern 64×64 panels use **pin 8** for line `E` (check the silkscreen next to the HUB75 input connector on your panel).
- Place a small solder bridge between the **center pad** and **`8`** (or **`16`** if your panel's silkscreen marks pin 16 as `E`).

Without this jumper, only half of the panel rows will display properly.

## Step 2: Wiring & Power

1. Plug the Matrix Portal M4 directly into the **HUB75 IN** (data-in) header on the back of the 64×64 panel, matching the key notch.
2. Connect the **5V 4A+ external power supply** to the panel's 5V/GND power harness (typically spade/fork terminals or a 4-pin power header).
   - Double-check polarity (`+5V` red, `GND` black) before applying power.
   - Connect the Matrix Portal M4's red/black power standoffs to the panel's power lugs **or** power the M4 logic via USB-C and keep grounds shared (do not back-feed 4A through a computer's USB port).
3. Connect a **USB-C data cable** from the Matrix Portal M4 to your host machine.

## Step 3: Flash the Phoenix M4 Firmware

Phoenix includes custom firmware in [`firmware/matrix_portal_m4/`](../../firmware/matrix_portal_m4/) that upgrades stock Protomatter with:

- **6-bit per-channel sRGB-to-linear LUT** — preserves full 6-bit color depth across R, G, and B instead of crushing shadows.
- **Hardware TCC0/WO[0] OE pulse dimming** — controls brightness on pin D16 (PB12) independently of the CPU, so low night-time brightness stays smooth and color-accurate (and emits zero pulses at brightness `0`).
- **Per-channel RGB calibration LUTs** — optional runtime override via serial command `0x08` (768 bytes, 256 entries each for R, G, B) or shared LUT via `0x01`.

### Install `arduino-cli` & Dependencies

```bash
# macOS (or see https://arduino.github.io/arduino-cli/installation/ on Linux)
brew install arduino-cli

# Add Adafruit SAMD board support
arduino-cli core update-index \
  --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
arduino-cli core install adafruit:samd \
  --additional-urls https://adafruit.github.io/arduino-board-index/package_adafruit_index.json

# Install exact required libraries (build.sh patches a temporary copy of Protomatter 1.7.1)
arduino-cli lib install \
  "Adafruit Protomatter@1.7.1" \
  "Adafruit GFX Library" \
  "Adafruit LIS3DH" \
  "Adafruit NeoPixel"
```

### Compile & Upload

Connect the Matrix Portal M4 to your computer via USB-C and run:

```bash
# Using just (default macOS port; pass port=/dev/ttyACM0 on Linux)
just flash-m4 port=/dev/cu.usbmodem101
```

Or manually:

```bash
cd firmware/matrix_portal_m4
bash build.sh /tmp/phoenix-m4
arduino-cli upload --fqbn adafruit:samd:adafruit_matrixportal_m4 --input-dir /tmp/phoenix-m4 -p /dev/ttyACM0 .
```

> **Tip:** `build.sh` patches a temporary copy of `Adafruit Protomatter@1.7.1` to hook the TCC0 OE pulse call cleanly without modifying your global Arduino libraries directory. If the M4 isn't detected on USB, double-tap its **Reset** button to enter the UF2 bootloader and retry.

### Verify Color & Timing Math (Optional)

```bash
c++ -std=c++11 -Wall -Wextra -Werror firmware/tests/panel_color_test.cpp -o /tmp/panel-color-test
/tmp/panel-color-test
```

## Step 4: Configure Phoenix

### All-in-One Host

Set your `.env`:

```env
PHOENIX_PLATFORM=serial
PHOENIX_SERIAL_PORT=/dev/ttyACM0     # /dev/cu.usbmodem101 on macOS
PHOENIX_SERIAL_BRIGHTNESS=200        # 0-255
```

Then launch Phoenix (via `docker compose up -d`, `./deploy/install.sh` on Linux, or `just dev-serial` on macOS).

### Split Host (Low-RAM Raspberry Pi + Home Server)

If a 1 GB Pi 3 drives your Matrix Portal M4, run `dashboard` + `render` on a home server and run `phoenix node` natively on the Pi — see [`docs/deployment.md`](../deployment.md#3-split-deployment-controller-server--paired-serial-player) for the full private HTTPS pairing setup.

## Color Calibration & Serial Protocol

The default firmware decodes incoming sRGB frames into linear intensity with equal R/G/B curves, which looks natural on most HUB75 panels out of the box.

For panels with a strong green or blue tint, you can push a custom per-channel LUT over serial without reflashing:

| Command | Header + Payload | Purpose |
|---|---|---|
| Frame | `DE AD BE EF` + `[brightness:1]` + `[RGB888:12288]` | Display a 64×64 frame at `brightness` (`0–255`) |
| `0x01` | `DE AD CA FE 01` + `[lut:256]` | Load shared 256-entry linear LUT |
| `0x02` | `DE AD CA FE 02` | Query 34-byte status packet (version, FPS, uptime, SCD40) |
| `0x03` | `DE AD CA FE 03` | Restore default sRGB LUT |
| `0x04` / `0x05` | `DE AD CA FE 04` / `05` | Screen off / screen on |
| `0x07` | `DE AD CA FE 07` + `[target:1]` + `[dur_100ms:1]` | Smooth hardware brightness fade |
| `0x08` | `DE AD CA FE 08` + `[R:256][G:256][B:256]` | Load calibrated per-channel linear LUTs (`0–255`) |

Custom LUTs take effect on the next frame and reset to sRGB on reboot.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Duplicate top/bottom halves or garbled rows | Bridge the **Address E** solder pad (`8` or `16`) on the back of the Matrix Portal M4. |
| Permission denied on `/dev/ttyACM0` (Linux) | Add your user to the `dialout` group (`sudo usermod -aG dialout "$USER"`) and re-login. |
| `build.sh` complains about Protomatter version | Run `arduino-cli lib install "Adafruit Protomatter@1.7.1"` (the patch targets 1.7.1 specifically). |
| Panel resets or dims unevenly on bright scenes | Use a dedicated 5V 4A+ PSU wired directly to the panel's power harness; avoid powering the panel through USB. |
