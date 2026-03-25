/**
 * Phoenix Frame Receiver — Matrix Portal M4
 *
 * Receives raw RGB888 frames over USB serial from a Raspberry Pi and displays
 * them on a 64x64 HUB75 LED panel using Adafruit Protomatter (DMA-driven).
 *
 * Protocol:
 *   [0xDE 0xAD 0xBE 0xEF] [brightness] [12288 bytes RGB888]
 *
 * The M4 does NO rendering — it is purely a dumb frame receiver and display
 * driver. If no frames arrive, the last valid frame is held indefinitely.
 *
 * Required libraries (install via Arduino Library Manager):
 *   - Adafruit Protomatter
 *   - Adafruit GFX Library
 *
 * Board: Adafruit Matrix Portal M4 (SAMD51)
 * Upload via Arduino IDE with Adafruit SAMD boards package installed.
 */

#include <Adafruit_Protomatter.h>

// --- Panel configuration ---
#define MATRIX_WIDTH  64
#define MATRIX_HEIGHT 64
#define BIT_DEPTH     6   // 6 bits = 64 levels per channel, max useful depth for this hardware

// --- Protocol constants ---
static const uint8_t MAGIC[4] = {0xDE, 0xAD, 0xBE, 0xEF};
#define FRAME_BYTES (MATRIX_WIDTH * MATRIX_HEIGHT * 3)  // 12,288
#define BRIGHTNESS_BYTE 1
#define PACKET_SIZE (sizeof(MAGIC) + BRIGHTNESS_BYTE + FRAME_BYTES)  // 12,293

// --- HUB75 pin definitions for Matrix Portal M4 ---
// Upper half: R1=7, G1=8, B1=9   Lower half: R2=10, G2=11, B2=12
// Clock=14, OE=15, Latch=16, Addr A=17, B=18, C=19, D=20, E=21
uint8_t rgbPins[]  = {7, 8, 9, 10, 11, 12};
uint8_t addrPins[] = {17, 18, 19, 20, 21};  // A, B, C, D, E — bridge solder jumper to "8" on board bottom
uint8_t clockPin   = 14;
uint8_t latchPin   = 15;
uint8_t oePin      = 16;

Adafruit_Protomatter matrix(
    MATRIX_WIDTH,        // width
    BIT_DEPTH,           // bit depth
    1, rgbPins,          // 1 chain of RGB data pins
    5, addrPins,         // 5 address lines (for 64 rows)
    clockPin, latchPin, oePin,
    true                 // double-buffer enabled
);

// --- Gamma correction LUT (gamma 2.0 — gentle correction for LED panels) ---
static const uint8_t PROGMEM gammaLUT[256] = {
      0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   1,   1,   1,   1,
      1,   1,   1,   1,   2,   2,   2,   2,   2,   3,   3,   3,   3,   4,   4,   4,
      4,   5,   5,   5,   6,   6,   6,   7,   7,   7,   8,   8,   9,   9,   9,  10,
     10,  11,  11,  12,  12,  13,  13,  14,  14,  15,  15,  16,  16,  17,  17,  18,
     18,  19,  20,  20,  21,  21,  22,  23,  23,  24,  25,  25,  26,  27,  27,  28,
     29,  29,  30,  31,  32,  32,  33,  34,  35,  35,  36,  37,  38,  38,  39,  40,
     41,  42,  42,  43,  44,  45,  46,  47,  47,  48,  49,  50,  51,  52,  53,  54,
     55,  55,  56,  57,  58,  59,  60,  61,  62,  63,  64,  65,  66,  67,  68,  69,
     70,  71,  72,  73,  74,  75,  76,  78,  79,  80,  81,  82,  83,  84,  85,  86,
     88,  89,  90,  91,  92,  93,  95,  96,  97,  98,  99, 101, 102, 103, 104, 106,
    107, 108, 109, 111, 112, 113, 115, 116, 117, 119, 120, 121, 123, 124, 125, 127,
    128, 129, 131, 132, 134, 135, 136, 138, 139, 141, 142, 144, 145, 146, 148, 149,
    151, 152, 154, 155, 157, 158, 160, 161, 163, 165, 166, 168, 169, 171, 172, 174,
    176, 177, 179, 180, 182, 184, 185, 187, 189, 190, 192, 194, 195, 197, 199, 200,
    202, 204, 206, 207, 209, 211, 213, 214, 216, 218, 220, 221, 223, 225, 227, 229,
    230, 232, 234, 236, 238, 240, 241, 243, 245, 247, 249, 251, 253, 254, 255, 255
};

// --- Receive buffer ---
static uint8_t frameBuf[FRAME_BYTES];

// --- State machine for header sync ---
static uint8_t syncIndex = 0;

/**
 * Read exactly `count` bytes from Serial into `buf`.
 * Returns true if all bytes received, false on timeout.
 */
bool readExact(uint8_t *buf, uint32_t count) {
    uint32_t received = 0;
    unsigned long deadline = millis() + 2000;  // 2s timeout per frame
    while (received < count) {
        if (millis() > deadline) return false;
        int avail = Serial.available();
        if (avail > 0) {
            int toRead = min((uint32_t)avail, count - received);
            int got = Serial.readBytes((char *)(buf + received), toRead);
            received += got;
            deadline = millis() + 2000;  // reset timeout on progress
        }
    }
    return true;
}

/**
 * Scan serial stream for the 4-byte magic header.
 * Returns true once all 4 magic bytes have been matched in sequence.
 */
bool syncToHeader() {
    while (Serial.available()) {
        uint8_t b = Serial.read();
        if (b == MAGIC[syncIndex]) {
            syncIndex++;
            if (syncIndex == sizeof(MAGIC)) {
                syncIndex = 0;
                return true;
            }
        } else {
            // Mismatch — check if this byte starts a new match
            syncIndex = (b == MAGIC[0]) ? 1 : 0;
        }
    }
    return false;
}

/**
 * Copy RGB888 receive buffer into the Protomatter framebuffer.
 * Applies brightness scaling and converts RGB888 → RGB565 on the fly.
 */
void copyFrameToMatrix(uint8_t brightness) {
    uint8_t *p = frameBuf;
    for (int y = 0; y < MATRIX_HEIGHT; y++) {
        for (int x = 0; x < MATRIX_WIDTH; x++) {
            uint8_t r = pgm_read_byte(&gammaLUT[*p++]);
            uint8_t g = pgm_read_byte(&gammaLUT[*p++]);
            uint8_t b = pgm_read_byte(&gammaLUT[*p++]);
            if (brightness < 255) {
                r = (uint8_t)((uint16_t)r * brightness / 255);
                g = (uint8_t)((uint16_t)g * brightness / 255);
                b = (uint8_t)((uint16_t)b * brightness / 255);
            }
            matrix.drawPixel(x, y, matrix.color565(r, g, b));
        }
    }
    matrix.show();  // swap double buffer — DMA picks it up on next scan
}

void setup() {
    Serial.begin(2000000);  // baud rate ignored for native USB CDC

    // Initialize Protomatter
    ProtomatterStatus status = matrix.begin();
    if (status != PROTOMATTER_OK) {
        // If matrix init fails, blink the onboard LED as an error signal
        pinMode(LED_BUILTIN, OUTPUT);
        while (true) {
            digitalWrite(LED_BUILTIN, HIGH);
            delay(100);
            digitalWrite(LED_BUILTIN, LOW);
            delay(100);
        }
    }

    // Start with a blank (black) screen
    matrix.fillScreen(0);
    matrix.show();
}

void loop() {
    // Phase 1: scan for magic header
    if (!syncToHeader()) {
        return;  // no complete header yet, come back next loop()
    }

    // Phase 2: read brightness byte
    uint8_t brightness;
    if (!readExact(&brightness, 1)) {
        return;  // timeout, will re-sync next iteration
    }

    // Phase 3: read full frame
    if (!readExact(frameBuf, FRAME_BYTES)) {
        return;  // timeout or disconnect, will re-sync next iteration
    }

    // Phase 4: display with brightness scaling
    copyFrameToMatrix(brightness);
}
