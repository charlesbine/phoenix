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

// --- Gamma correction LUT (gamma 1.6 — preserves shadow detail, less crushing) ---
static const uint8_t PROGMEM gammaLUT[256] = {
      0,   0,   0,   0,   0,   0,   1,   1,   1,   1,   1,   2,   2,   2,   2,   3,
      3,   3,   4,   4,   4,   5,   5,   5,   6,   6,   7,   7,   7,   8,   8,   9,
      9,  10,  10,  11,  11,  12,  12,  13,  13,  14,  14,  15,  15,  16,  16,  17,
     18,  18,  19,  19,  20,  21,  21,  22,  23,  23,  24,  25,  25,  26,  27,  27,
     28,  29,  29,  30,  31,  31,  32,  33,  34,  34,  35,  36,  37,  38,  38,  39,
     40,  41,  42,  42,  43,  44,  45,  46,  46,  47,  48,  49,  50,  51,  52,  53,
     53,  54,  55,  56,  57,  58,  59,  60,  61,  62,  63,  64,  64,  65,  66,  67,
     68,  69,  70,  71,  72,  73,  74,  75,  76,  77,  78,  79,  80,  81,  83,  84,
     85,  86,  87,  88,  89,  90,  91,  92,  93,  94,  95,  97,  98,  99, 100, 101,
    102, 103, 104, 106, 107, 108, 109, 110, 111, 113, 114, 115, 116, 117, 119, 120,
    121, 122, 123, 125, 126, 127, 128, 130, 131, 132, 133, 135, 136, 137, 138, 140,
    141, 142, 143, 145, 146, 147, 149, 150, 151, 153, 154, 155, 157, 158, 159, 161,
    162, 163, 165, 166, 167, 169, 170, 171, 173, 174, 176, 177, 178, 180, 181, 183,
    184, 185, 187, 188, 190, 191, 193, 194, 196, 197, 198, 200, 201, 203, 204, 206,
    207, 209, 210, 212, 213, 215, 216, 218, 219, 221, 222, 224, 225, 227, 228, 230,
    231, 233, 235, 236, 238, 239, 241, 242, 244, 245, 247, 249, 250, 252, 253, 255
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
