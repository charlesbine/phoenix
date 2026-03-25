/**
 * Standalone color test — cycles red, green, blue forever.
 * No serial, no external input. Just Protomatter driving the panel.
 */

#include <Adafruit_Protomatter.h>

#define MATRIX_WIDTH  64
#define MATRIX_HEIGHT 64
#define BIT_DEPTH     6

uint8_t rgbPins[]  = {7, 8, 9, 10, 11, 12};
uint8_t addrPins[] = {17, 18, 19, 20, 21};
uint8_t clockPin   = 14;
uint8_t latchPin   = 15;
uint8_t oePin      = 16;

Adafruit_Protomatter matrix(
    MATRIX_WIDTH, BIT_DEPTH,
    1, rgbPins,
    5, addrPins,
    clockPin, latchPin, oePin,
    true
);

void setup() {
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
}

void loop() {
    // Red
    matrix.fillScreen(matrix.color565(255, 0, 0));
    matrix.show();
    delay(2000);

    // Green
    matrix.fillScreen(matrix.color565(0, 255, 0));
    matrix.show();
    delay(2000);

    // Blue
    matrix.fillScreen(matrix.color565(0, 0, 255));
    matrix.show();
    delay(2000);

    // White
    matrix.fillScreen(matrix.color565(255, 255, 255));
    matrix.show();
    delay(2000);
}
