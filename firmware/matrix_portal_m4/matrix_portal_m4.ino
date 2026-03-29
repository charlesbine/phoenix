/**
 * Phoenix Frame Receiver v2.1 — Matrix Portal M4
 *
 * Protocol v2:
 *   Frame:   [0xDE 0xAD 0xBE 0xEF] [brightness] [12288 bytes RGB888]
 *   Command: [0xDE 0xAD 0xCA 0xFE] [cmd] [payload...]
 *   Response:[0xFE 0xED 0xBA 0xCE] [data...]
 *
 * Commands:
 *   0x01 — Update LUT (256 bytes follow)
 *   0x02 — Get Status (returns 36-byte struct)
 *   0x03 — Reset LUT to default
 *   0x04 — Screen off (stop scanning, fill black)
 *   0x05 — Screen on (resume scanning)
 *   0x06 — Set SCD40 interval (2 bytes: seconds, big-endian)
 *   0x07 — Brightness fade (2 bytes: target brightness, duration in 100ms units)
 *
 * Required libraries:
 *   - Adafruit Protomatter
 *   - Adafruit GFX Library
 *   - Adafruit LIS3DH
 *   - Adafruit NeoPixel
 */

#include <Adafruit_Protomatter.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_LIS3DH.h>
#include "splash_logo.h"

// --- Firmware version ---
#define FW_VERSION_MAJOR 2
#define FW_VERSION_MINOR 1

// --- Minimal SCD40 I2C driver ---
#define SCD40_ADDR 0x62
class SCD40 {
public:
    bool begin() {
        Wire.beginTransmission(SCD40_ADDR);
        if (Wire.endTransmission() != 0) return false;
        Wire.beginTransmission(SCD40_ADDR);
        Wire.write(0x21); Wire.write(0xB1);  // start periodic measurement
        Wire.endTransmission();
        delay(1);
        return true;
    }
    bool dataReady() {
        Wire.beginTransmission(SCD40_ADDR);
        Wire.write(0xE4); Wire.write(0xB8);
        Wire.endTransmission();
        delay(1);
        Wire.requestFrom(SCD40_ADDR, 3);
        if (Wire.available() < 3) return false;
        uint16_t val = (Wire.read() << 8) | Wire.read();
        Wire.read();
        return (val & 0x07FF) != 0;
    }
    bool read(uint16_t &co2, float &temp, float &hum) {
        Wire.beginTransmission(SCD40_ADDR);
        Wire.write(0xEC); Wire.write(0x05);
        Wire.endTransmission();
        delay(1);
        Wire.requestFrom(SCD40_ADDR, 9);
        if (Wire.available() < 9) return false;
        co2 = (Wire.read() << 8) | Wire.read(); Wire.read();
        uint16_t rawT = (Wire.read() << 8) | Wire.read(); Wire.read();
        uint16_t rawH = (Wire.read() << 8) | Wire.read(); Wire.read();
        temp = -45.0f + 175.0f * rawT / 65535.0f;
        hum = 100.0f * rawH / 65535.0f;
        return true;
    }
};

// --- Panel ---
#define MATRIX_WIDTH  64
#define MATRIX_HEIGHT 64
#define BIT_DEPTH     6

// --- Protocol ---
static const uint8_t MAGIC_FRAME[4] = {0xDE, 0xAD, 0xBE, 0xEF};
static const uint8_t MAGIC_CMD[4]   = {0xDE, 0xAD, 0xCA, 0xFE};
static const uint8_t MAGIC_RESP[4]  = {0xFE, 0xED, 0xBA, 0xCE};
#define FRAME_BYTES (MATRIX_WIDTH * MATRIX_HEIGHT * 3)

// Commands
#define CMD_UPDATE_LUT     0x01
#define CMD_GET_STATUS     0x02
#define CMD_RESET_LUT      0x03
#define CMD_SCREEN_OFF     0x04
#define CMD_SCREEN_ON      0x05
#define CMD_SET_SCD_INTERVAL 0x06
#define CMD_BRIGHTNESS_FADE  0x07

// --- Pins ---
uint8_t rgbPins[]  = {7, 8, 9, 10, 11, 12};
uint8_t addrPins[] = {17, 18, 19, 20, 21};
uint8_t clockPin   = 14;
uint8_t latchPin   = 15;
uint8_t oePin      = 16;

#define BUTTON_UP    2
#define BUTTON_DOWN  3
#define LIGHT_SENSOR A4
#define NEOPIXEL_PIN 4

// --- Hardware ---
Adafruit_Protomatter matrix(
    MATRIX_WIDTH, BIT_DEPTH,
    1, rgbPins, 5, addrPins,
    clockPin, latchPin, oePin,
    true
);

Adafruit_NeoPixel neopixel(1, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
SCD40 scd4x;
Adafruit_LIS3DH lis3dh;

// --- Default gamma LUT (gamma 1.6) ---
static const uint8_t PROGMEM defaultLUT[256] = {
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

// --- State ---
static uint8_t activeLUT[256];
static uint8_t gammaX10 = 16;
static bool lutIsCustom = false;

static uint8_t frameBuf[FRAME_BYTES];

// Sensor state
static bool scdOk = false;
static bool lisOk = false;
static int16_t  scdTempC10   = -999;
static uint16_t scdHumidity  = 0;
static uint16_t scdCo2       = 0;
static unsigned long lastScdRead = 0;
static uint32_t scdInterval = 30000;  // configurable

// Frame stats
static uint32_t framesTotal = 0;
static uint16_t fpsX10 = 0;
static uint32_t fpsFrameCount = 0;
static unsigned long fpsLastCalc = 0;
static unsigned long lastFrameTime = 0;
static uint8_t  syncErrors = 0;
static uint8_t  currentBrightness = 255;

// Screen state
static bool screenOn = true;

// Brightness fade
static bool fading = false;
static uint8_t fadeTarget = 255;
static uint8_t fadeStart = 255;
static unsigned long fadeStartTime = 0;
static unsigned long fadeDuration = 0;

// Watchdog — auto-restart if no frames for 60s
#define WATCHDOG_TIMEOUT 60000

// Sync buffer
static uint8_t syncBuf[4];

// --- Status struct (36 bytes) ---
#pragma pack(push, 1)
struct StatusResponse {
    uint8_t  magic[4];        // 0xFE 0xED 0xBA 0xCE
    uint8_t  fwMajor;         // firmware version major
    uint8_t  fwMinor;         // firmware version minor
    int16_t  scdTempC10;      // SCD40 temp × 10
    uint16_t scdHumidity10;   // humidity × 10
    uint16_t scdCo2;          // CO2 ppm
    uint32_t uptimeSec;       // seconds since boot
    uint32_t framesTotal;     // frames received
    uint16_t fpsX10;          // FPS × 10
    uint8_t  brightness;      // current brightness
    uint8_t  gammaX10;        // gamma × 10
    uint8_t  syncErrors;      // rolling error count
    uint8_t  scdOk;           // 1 if SCD40 detected
    uint16_t lightLevel;      // ambient light (0-4095)
    uint8_t  buttonUp;        // 1 if pressed
    uint8_t  buttonDown;      // 1 if pressed
    uint8_t  screenOn;        // 1 if screen is on
    uint8_t  lisOk;           // 1 if accelerometer detected
    uint16_t reserved;        // padding to 36 bytes
};
#pragma pack(pop)


// --- Functions ---

bool readExact(uint8_t *buf, uint32_t count) {
    uint32_t received = 0;
    unsigned long deadline = millis() + 2000;
    while (received < count) {
        if (millis() > deadline) return false;
        int avail = Serial.available();
        if (avail > 0) {
            int toRead = min((uint32_t)avail, count - received);
            int got = Serial.readBytes((char *)(buf + received), toRead);
            received += got;
            deadline = millis() + 2000;
        }
    }
    return true;
}


void copyFrameToMatrix(uint8_t brightness) {
    uint8_t *p = frameBuf;
    for (int y = 0; y < MATRIX_HEIGHT; y++) {
        for (int x = 0; x < MATRIX_WIDTH; x++) {
            uint8_t r = activeLUT[*p++];
            uint8_t g = activeLUT[*p++];
            uint8_t b = activeLUT[*p++];
            if (brightness < 255) {
                r = (uint8_t)((uint16_t)r * brightness / 255);
                g = (uint8_t)((uint16_t)g * brightness / 255);
                b = (uint8_t)((uint16_t)b * brightness / 255);
            }
            matrix.drawPixel(x, y, matrix.color565(r, g, b));
        }
    }
    matrix.show();
}


void initLUT() {
    for (int i = 0; i < 256; i++) {
        activeLUT[i] = pgm_read_byte(&defaultLUT[i]);
    }
    lutIsCustom = false;
    gammaX10 = 16;
}


void sendAck() {
    Serial.write(MAGIC_RESP, 4);
    Serial.write(0x01);
    Serial.flush();
}


void showBootSplash() {
    // Display the Phoenix logo from PROGMEM
    for (int y = 0; y < MATRIX_HEIGHT; y++) {
        for (int x = 0; x < MATRIX_WIDTH; x++) {
            uint16_t color = pgm_read_word(&splashLogo[y * MATRIX_WIDTH + x]);
            matrix.drawPixel(x, y, color);
        }
    }
    matrix.show();
}


void handleCommand() {
    uint8_t cmd;
    if (!readExact(&cmd, 1)) return;

    switch (cmd) {
        case CMD_UPDATE_LUT: {
            uint8_t newLut[256];
            if (readExact(newLut, 256)) {
                memcpy(activeLUT, newLut, 256);
                lutIsCustom = true;
                gammaX10 = 0;
                sendAck();
            }
            break;
        }
        case CMD_GET_STATUS: {
            StatusResponse resp;
            memcpy(resp.magic, MAGIC_RESP, 4);
            resp.fwMajor       = FW_VERSION_MAJOR;
            resp.fwMinor       = FW_VERSION_MINOR;
            resp.scdTempC10    = scdTempC10;
            resp.scdHumidity10 = scdHumidity;
            resp.scdCo2        = scdCo2;
            resp.uptimeSec     = millis() / 1000;
            resp.framesTotal   = framesTotal;
            resp.fpsX10        = fpsX10;
            resp.brightness    = currentBrightness;
            resp.gammaX10      = gammaX10;
            resp.syncErrors    = syncErrors;
            resp.scdOk         = scdOk ? 1 : 0;
            resp.lightLevel    = analogRead(LIGHT_SENSOR);
            resp.buttonUp      = !digitalRead(BUTTON_UP) ? 1 : 0;
            resp.buttonDown    = !digitalRead(BUTTON_DOWN) ? 1 : 0;
            resp.screenOn      = screenOn ? 1 : 0;
            resp.lisOk         = lisOk ? 1 : 0;
            resp.reserved      = 0;
            Serial.write((uint8_t *)&resp, sizeof(resp));
            Serial.flush();
            break;
        }
        case CMD_RESET_LUT: {
            initLUT();
            sendAck();
            break;
        }
        case CMD_SCREEN_OFF: {
            screenOn = false;
            matrix.fillScreen(0);
            matrix.show();
            neopixel.setPixelColor(0, neopixel.Color(1, 0, 1));  // dim purple = screen off
            neopixel.show();
            sendAck();
            break;
        }
        case CMD_SCREEN_ON: {
            screenOn = true;
            sendAck();
            break;
        }
        case CMD_SET_SCD_INTERVAL: {
            uint8_t buf[2];
            if (readExact(buf, 2)) {
                scdInterval = ((uint32_t)buf[0] << 8 | buf[1]) * 1000UL;
                if (scdInterval < 5000) scdInterval = 5000;    // min 5s
                if (scdInterval > 600000) scdInterval = 600000; // max 10min
                sendAck();
            }
            break;
        }
        case CMD_BRIGHTNESS_FADE: {
            uint8_t buf[2];
            if (readExact(buf, 2)) {
                fadeTarget = buf[0];
                fadeDuration = (uint32_t)buf[1] * 100UL;  // duration in 100ms units
                fadeStart = currentBrightness;
                fadeStartTime = millis();
                fading = true;
                sendAck();
            }
            break;
        }
    }
}


void updateBrightnessFade() {
    if (!fading) return;

    unsigned long elapsed = millis() - fadeStartTime;
    if (elapsed >= fadeDuration) {
        currentBrightness = fadeTarget;
        fading = false;
    } else {
        float progress = (float)elapsed / fadeDuration;
        currentBrightness = fadeStart + (int16_t)(fadeTarget - fadeStart) * progress;
    }
}


void readSensors() {
    if (!scdOk) return;
    if (millis() - lastScdRead < scdInterval) return;
    lastScdRead = millis();

    if (scd4x.dataReady()) {
        uint16_t co2 = 0;
        float temp = 0, hum = 0;
        if (scd4x.read(co2, temp, hum)) {
            scdTempC10  = (int16_t)(temp * 10);
            scdHumidity = (uint16_t)(hum * 10);
            scdCo2      = co2;
        }
    }
}


void updateNeopixel() {
    if (!screenOn) return;  // don't override screen-off indicator

    unsigned long gap = (lastFrameTime > 0) ? (millis() - lastFrameTime) : 999999;
    if (gap < 5000) {
        neopixel.setPixelColor(0, neopixel.Color(0, 4, 0));   // dim green
    } else if (gap < 30000) {
        neopixel.setPixelColor(0, neopixel.Color(4, 2, 0));   // dim amber
    } else {
        neopixel.setPixelColor(0, neopixel.Color(4, 0, 0));   // dim red
    }
    neopixel.show();
}


void checkWatchdog() {
    // If no frames for 60s and we previously had frames, soft-reset display
    if (framesTotal > 0 && lastFrameTime > 0) {
        if (millis() - lastFrameTime > WATCHDOG_TIMEOUT) {
            // Show boot splash to indicate we're alive but lost connection
            showBootSplash();
            lastFrameTime = millis();  // reset timer so we don't spam
        }
    }
}


void setup() {
    Serial.begin(2000000);

    pinMode(BUTTON_UP, INPUT_PULLUP);
    pinMode(BUTTON_DOWN, INPUT_PULLUP);
    pinMode(LIGHT_SENSOR, INPUT);

    neopixel.begin();
    neopixel.setBrightness(10);
    neopixel.setPixelColor(0, neopixel.Color(0, 0, 4));  // blue = booting
    neopixel.show();

    initLUT();

    ProtomatterStatus status = matrix.begin();
    if (status != PROTOMATTER_OK) {
        pinMode(LED_BUILTIN, OUTPUT);
        while (true) {
            digitalWrite(LED_BUILTIN, HIGH); delay(100);
            digitalWrite(LED_BUILTIN, LOW); delay(100);
        }
    }

    // Boot splash — warm amber gradient
    showBootSplash();

    // I2C sensors
    Wire.begin();
    scdOk = scd4x.begin();
    if (lis3dh.begin(0x19)) {
        lis3dh.setRange(LIS3DH_RANGE_2_G);
        lisOk = true;
    }

    neopixel.setPixelColor(0, neopixel.Color(4, 2, 0));  // amber = waiting for Pi
    neopixel.show();
}


void loop() {
    // --- Periodic tasks ---
    readSensors();
    updateBrightnessFade();

    if (millis() - fpsLastCalc >= 2000) {
        fpsX10 = (uint16_t)(fpsFrameCount * 10000UL / max(1UL, millis() - fpsLastCalc));
        fpsFrameCount = 0;
        fpsLastCalc = millis();
        updateNeopixel();
        checkWatchdog();
    }

    // --- Serial processing ---
    while (Serial.available()) {
        uint8_t b = Serial.read();

        syncBuf[0] = syncBuf[1];
        syncBuf[1] = syncBuf[2];
        syncBuf[2] = syncBuf[3];
        syncBuf[3] = b;

        // Frame magic
        if (memcmp(syncBuf, MAGIC_FRAME, 4) == 0) {
            uint8_t brightness;
            if (!readExact(&brightness, 1)) continue;
            if (!readExact(frameBuf, FRAME_BYTES)) { syncErrors++; continue; }

            // Apply fade override if active
            if (fading) {
                brightness = currentBrightness;
            } else {
                currentBrightness = brightness;
            }

            if (screenOn) {
                copyFrameToMatrix(brightness);
            }

            framesTotal++;
            fpsFrameCount++;
            lastFrameTime = millis();
            memset(syncBuf, 0, 4);
            return;
        }

        // Command magic
        if (memcmp(syncBuf, MAGIC_CMD, 4) == 0) {
            handleCommand();
            memset(syncBuf, 0, 4);
            return;
        }
    }
}
