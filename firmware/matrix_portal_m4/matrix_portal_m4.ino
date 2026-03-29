/**
 * Phoenix Frame Receiver v2 — Matrix Portal M4
 *
 * Receives raw RGB888 frames over USB serial from a Raspberry Pi and displays
 * them on a 64x64 HUB75 LED panel using Adafruit Protomatter (DMA-driven).
 *
 * Protocol v2:
 *   Frame:   [0xDE 0xAD 0xBE 0xEF] [brightness] [12288 bytes RGB888]
 *   Command: [0xDE 0xAD 0xCA 0xFE] [cmd] [payload...]
 *   Response:[0xFE 0xED 0xBA 0xCK] [data...]
 *
 * Commands:
 *   0x01 — Update LUT (256 bytes follow)
 *   0x02 — Get Status (returns 32-byte struct)
 *   0x03 — Reset LUT to default
 *
 * Sensors:
 *   - SAMD51 internal die temperature
 *   - SCD40 temperature/humidity/CO2 (I2C, optional)
 *   - LIS3DH accelerometer (I2C, on-board)
 *   - Light sensor (analog, on-board)
 *   - Buttons (UP/DOWN, on-board)
 *
 * Required libraries:
 *   - Adafruit Protomatter
 *   - Adafruit GFX Library
 *   - Adafruit SCD4x
 *   - Adafruit LIS3DH
 *   - Adafruit NeoPixel
 */

#include <Adafruit_Protomatter.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>

// Optional sensors — fail gracefully if not connected
#include <Adafruit_LIS3DH.h>

// Minimal SCD40 I2C driver (no external library needed)
#define SCD40_ADDR 0x62
class SCD40 {
public:
    bool begin() {
        Wire.beginTransmission(SCD40_ADDR);
        if (Wire.endTransmission() != 0) return false;
        // Start periodic measurement: command 0x21B1
        Wire.beginTransmission(SCD40_ADDR);
        Wire.write(0x21); Wire.write(0xB1);
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
        Wire.read(); // CRC
        return (val & 0x07FF) != 0;
    }
    bool read(uint16_t &co2, float &temp, float &hum) {
        Wire.beginTransmission(SCD40_ADDR);
        Wire.write(0xEC); Wire.write(0x05);
        Wire.endTransmission();
        delay(1);
        Wire.requestFrom(SCD40_ADDR, 9);
        if (Wire.available() < 9) return false;
        co2 = (Wire.read() << 8) | Wire.read(); Wire.read(); // CRC
        uint16_t rawT = (Wire.read() << 8) | Wire.read(); Wire.read();
        uint16_t rawH = (Wire.read() << 8) | Wire.read(); Wire.read();
        temp = -45.0f + 175.0f * rawT / 65535.0f;
        hum = 100.0f * rawH / 65535.0f;
        return true;
    }
};

// --- Panel configuration ---
#define MATRIX_WIDTH  64
#define MATRIX_HEIGHT 64
#define BIT_DEPTH     6

// --- Protocol constants ---
static const uint8_t MAGIC_FRAME[4] = {0xDE, 0xAD, 0xBE, 0xEF};
static const uint8_t MAGIC_CMD[4]   = {0xDE, 0xAD, 0xCA, 0xFE};
static const uint8_t MAGIC_RESP[4]  = {0xFE, 0xED, 0xBA, 0xCE};
#define FRAME_BYTES (MATRIX_WIDTH * MATRIX_HEIGHT * 3)

// Commands
#define CMD_UPDATE_LUT  0x01
#define CMD_GET_STATUS  0x02
#define CMD_RESET_LUT   0x03

// --- Pin definitions ---
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
    true  // double-buffer
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

// --- Active LUT (RAM copy, updatable via serial) ---
static uint8_t activeLUT[256];
static uint8_t gammaX10 = 16;  // 1.6 × 10
static bool lutIsCustom = false;

// --- Buffers ---
static uint8_t frameBuf[FRAME_BYTES];

// --- Sensor state ---
static bool scdOk = false;
static bool lisOk = false;
static int16_t  scdTempC10   = -999;  // × 10
static uint16_t scdHumidity  = 0;     // × 10
static uint16_t scdCo2       = 0;
static unsigned long lastScdRead = 0;
#define SCD_INTERVAL 30000  // 30 seconds

// --- Frame stats ---
static uint32_t framesTotal = 0;
static uint16_t fpsX10 = 0;
static uint32_t fpsFrameCount = 0;
static unsigned long fpsLastCalc = 0;
static uint8_t  syncErrors = 0;
static uint8_t  currentBrightness = 255;

// --- Header sync state machine ---
static uint8_t syncBuf[4];
static uint8_t syncIdx = 0;

// --- Status response struct (32 bytes) ---
#pragma pack(push, 1)
struct StatusResponse {
    uint8_t  magic[4];        // 0xFE 0xED 0xBA 0xCE
    int16_t  dieTempC10;      // SAMD51 die temp × 10
    uint16_t supplyMv;        // supply voltage mV
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
};
#pragma pack(pop)


// --- Forward declarations ---
bool readExact(uint8_t *buf, uint32_t count);
void copyFrameToMatrix(uint8_t brightness);
void handleCommand();
void sendStatus();
void readSensors();
int16_t readDieTemp();
uint16_t readSupplyVoltage();
void updateNeopixel();
void initLUT();


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


void handleCommand() {
    uint8_t cmd;
    if (!readExact(&cmd, 1)) return;

    switch (cmd) {
        case CMD_UPDATE_LUT: {
            uint8_t newLut[256];
            if (readExact(newLut, 256)) {
                memcpy(activeLUT, newLut, 256);
                lutIsCustom = true;
                gammaX10 = 0;  // custom, unknown gamma
                // ACK
                Serial.write(MAGIC_RESP, 4);
                Serial.write(0x01);
                Serial.flush();
            }
            break;
        }
        case CMD_GET_STATUS: {
            sendStatus();
            break;
        }
        case CMD_RESET_LUT: {
            initLUT();
            Serial.write(MAGIC_RESP, 4);
            Serial.write(0x01);
            Serial.flush();
            break;
        }
    }
}


int16_t readDieTemp() {
    // SAMD51 internal temperature sensor via SUPC TSEN
    // Use the calibration data from NVM if available, otherwise approximate
    analogReadResolution(12);
    // SAMD51 doesn't expose die temp through simple analogRead
    // Return a placeholder — real implementation needs direct register access
    // For now, use the SCD40 ambient temp if available
    return scdOk ? scdTempC10 : -999;
}


uint16_t readSupplyVoltage() {
    // No battery ADC on Matrix Portal M4 — it's USB powered
    // Return nominal USB voltage
    return 5000;
}


void sendStatus() {
    StatusResponse resp;
    memcpy(resp.magic, MAGIC_RESP, 4);
    resp.dieTempC10    = readDieTemp();
    resp.supplyMv      = readSupplyVoltage();
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
    resp.buttonUp      = !digitalRead(BUTTON_UP) ? 1 : 0;    // active low
    resp.buttonDown    = !digitalRead(BUTTON_DOWN) ? 1 : 0;

    Serial.write((uint8_t *)&resp, sizeof(resp));
    Serial.flush();
}


void readSensors() {
    if (!scdOk) return;
    if (millis() - lastScdRead < SCD_INTERVAL) return;
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
    // Green = frames flowing, amber = no frames for 5s, red = no frames for 30s
    static unsigned long lastFrameTime = 0;
    if (framesTotal > 0) {
        unsigned long gap = millis() - lastFrameTime;
        if (gap < 5000) {
            neopixel.setPixelColor(0, neopixel.Color(0, 4, 0));  // dim green
        } else if (gap < 30000) {
            neopixel.setPixelColor(0, neopixel.Color(4, 2, 0));  // dim amber
        } else {
            neopixel.setPixelColor(0, neopixel.Color(4, 0, 0));  // dim red
        }
    } else {
        neopixel.setPixelColor(0, neopixel.Color(0, 0, 4));  // dim blue = waiting
    }
    neopixel.show();
    if (framesTotal > 0) lastFrameTime = millis();
}


void setup() {
    Serial.begin(2000000);

    // Buttons
    pinMode(BUTTON_UP, INPUT_PULLUP);
    pinMode(BUTTON_DOWN, INPUT_PULLUP);

    // Light sensor
    pinMode(LIGHT_SENSOR, INPUT);

    // Neopixel
    neopixel.begin();
    neopixel.setBrightness(10);  // very dim — it's in a box
    neopixel.setPixelColor(0, neopixel.Color(0, 0, 4));  // blue = booting
    neopixel.show();

    // Initialize LUT from PROGMEM defaults
    initLUT();

    // Initialize Protomatter
    ProtomatterStatus status = matrix.begin();
    if (status != PROTOMATTER_OK) {
        pinMode(LED_BUILTIN, OUTPUT);
        while (true) {
            digitalWrite(LED_BUILTIN, HIGH);
            delay(100);
            digitalWrite(LED_BUILTIN, LOW);
            delay(100);
        }
    }

    matrix.fillScreen(0);
    matrix.show();

    // I2C sensors
    Wire.begin();

    // SCD40
    scdOk = scd4x.begin();

    // LIS3DH accelerometer
    if (lis3dh.begin(0x19)) {
        lis3dh.setRange(LIS3DH_RANGE_2_G);
        lisOk = true;
    }
}


void loop() {
    // --- Periodic tasks (non-blocking) ---
    readSensors();

    // FPS calculation (every 2 seconds)
    if (millis() - fpsLastCalc >= 2000) {
        fpsX10 = (uint16_t)(fpsFrameCount * 10000UL / max(1UL, millis() - fpsLastCalc));
        fpsFrameCount = 0;
        fpsLastCalc = millis();
        updateNeopixel();
    }

    // --- Serial processing ---
    while (Serial.available()) {
        uint8_t b = Serial.read();

        // Shift into sync buffer
        syncBuf[0] = syncBuf[1];
        syncBuf[1] = syncBuf[2];
        syncBuf[2] = syncBuf[3];
        syncBuf[3] = b;

        // Check for frame magic
        if (memcmp(syncBuf, MAGIC_FRAME, 4) == 0) {
            // Read frame
            uint8_t brightness;
            if (!readExact(&brightness, 1)) continue;
            if (!readExact(frameBuf, FRAME_BYTES)) { syncErrors++; continue; }

            currentBrightness = brightness;
            copyFrameToMatrix(brightness);
            framesTotal++;
            fpsFrameCount++;
            memset(syncBuf, 0, 4);  // reset sync buffer
            return;  // process one frame per loop iteration
        }

        // Check for command magic
        if (memcmp(syncBuf, MAGIC_CMD, 4) == 0) {
            handleCommand();
            memset(syncBuf, 0, 4);
            return;
        }
    }
}
