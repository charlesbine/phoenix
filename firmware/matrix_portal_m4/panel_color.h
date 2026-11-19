#pragma once

#include <stdint.h>

namespace panel {

constexpr uint8_t Width = 64;
constexpr uint8_t Height = 64;
constexpr uint8_t BitDepth = 6;
constexpr uint8_t MaxLevel = (1u << BitDepth) - 1;
constexpr uint8_t Channels = 3;
constexpr uint16_t LutSize = 256;

// Standard sRGB EOTF, rounded once to the native 0–63 PWM range.
constexpr uint8_t SrgbLut[LutSize] = {
     0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
     0,  0,  0,  0,  0,  0,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,
     1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  2,  2,  2,  2,  2,
     2,  2,  2,  2,  2,  2,  2,  2,  2,  3,  3,  3,  3,  3,  3,  3,
     3,  3,  3,  4,  4,  4,  4,  4,  4,  4,  4,  4,  5,  5,  5,  5,
     5,  5,  5,  5,  6,  6,  6,  6,  6,  6,  6,  7,  7,  7,  7,  7,
     7,  8,  8,  8,  8,  8,  8,  9,  9,  9,  9,  9,  9, 10, 10, 10,
    10, 10, 11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 13, 13, 13, 13,
    14, 14, 14, 14, 15, 15, 15, 15, 16, 16, 16, 16, 17, 17, 17, 17,
    18, 18, 18, 18, 19, 19, 19, 19, 20, 20, 20, 21, 21, 21, 22, 22,
    22, 22, 23, 23, 23, 24, 24, 24, 25, 25, 25, 26, 26, 26, 27, 27,
    27, 28, 28, 28, 29, 29, 29, 30, 30, 31, 31, 31, 32, 32, 32, 33,
    33, 34, 34, 34, 35, 35, 36, 36, 36, 37, 37, 38, 38, 38, 39, 39,
    40, 40, 41, 41, 41, 42, 42, 43, 43, 44, 44, 45, 45, 46, 46, 46,
    47, 47, 48, 48, 49, 49, 50, 50, 51, 51, 52, 52, 53, 53, 54, 54,
    55, 55, 56, 56, 57, 58, 58, 59, 59, 60, 60, 61, 61, 62, 62, 63,
};

inline uint8_t quantizeLinear(uint8_t value) {
    return (uint16_t(value) * MaxLevel + 127) / 255;
}

// Protomatter's SAMD51 byte format stores GPIO changes between pixels.
// RGB is reset before each plane and the clock is low for the first column.
inline void encodeRowPair(uint8_t *dest, const uint8_t *upper, const uint8_t *lower,
                          const uint8_t *pinMasks, uint8_t clockMask) {
    for (uint8_t bit = 1; bit <= MaxLevel; bit <<= 1) {
        uint8_t prior = 0;
        for (uint8_t x = 0; x < Width; ++x) {
            const uint8_t *a = upper + x * Channels;
            const uint8_t *b = lower + x * Channels;
            uint8_t pins = 0;
            for (uint8_t c = 0; c < Channels; ++c) {
                if (a[c] & bit) pins |= pinMasks[c];
                if (b[c] & bit) pins |= pinMasks[c + Channels];
            }
            *dest++ = pins ^ prior;
            prior = pins | clockMask;
        }
    }
}

// The pulse starts before Protomatter starts the scan interval. Leave the
// last tick of the one-shot for the inactive level, including at full power.
inline uint32_t oePulseTicks(uint32_t period, uint8_t brightness) {
    const uint32_t ticks = (period * brightness + 127) / 255;
    return ticks < period ? ticks : period - 1;
}

} // namespace panel
