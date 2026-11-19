#include "../matrix_portal_m4/panel_color.h"

#include <cassert>
#include <cmath>

int main() {
    for (int code = 0; code < panel::LutSize; ++code) {
        const double srgb = code / 255.0;
        const double linear = srgb <= 0.04045 ? srgb / 12.92
            : std::pow((srgb + 0.055) / 1.055, 2.4);
        assert(panel::SrgbLut[code] == std::lround(linear * panel::MaxLevel));
        assert(panel::quantizeLinear(code) == std::lround(code / 255.0 * panel::MaxLevel));
    }

    constexpr uint8_t masks[] = {1, 4, 16, 2, 8, 32};
    constexpr uint8_t clock = 64;
    uint8_t upper[panel::Width * panel::Channels] = {};
    uint8_t lower[panel::Width * panel::Channels] = {};
    uint8_t data[panel::Width * panel::BitDepth] = {};
    // Each channel gets all 64 codes. Different offsets expose swapped pins,
    // and using both halves verifies the row pair and the toggle format.
    for (int x = 0; x < panel::Width; ++x) {
        for (int c = 0; c < panel::Channels; ++c) {
            upper[x * panel::Channels + c] = (x + 7 * c) % 64;
            lower[x * panel::Channels + c] = (3 * x + 13 * c) % 64;
        }
    }
    panel::encodeRowPair(data, upper, lower, masks, clock);
    for (int plane = 0; plane < panel::BitDepth; ++plane) {
        uint8_t pins = 0;
        for (int x = 0; x < panel::Width; ++x) {
            pins ^= data[plane * panel::Width + x];
            assert(!(pins & clock));
            for (int c = 0; c < panel::Channels; ++c) {
                assert(bool(pins & masks[c]) == bool(upper[x * panel::Channels + c] & (1 << plane)));
                assert(bool(pins & masks[c + panel::Channels]) ==
                       bool(lower[x * panel::Channels + c] & (1 << plane)));
            }
            pins ^= clock;
        }
    }

    for (uint32_t period = 95; period <= 95u << (panel::BitDepth - 1); period <<= 1) {
        assert(panel::oePulseTicks(period, 0) == 0);
        assert(panel::oePulseTicks(period, 255) == period - 1);
        uint32_t previous = 0;
        for (int brightness = 1; brightness < 255; ++brightness) {
            const auto ticks = panel::oePulseTicks(period, brightness);
            assert(ticks >= previous && ticks < period);
            assert(std::fabs(ticks - std::fmin(period - 1, period * brightness / 255.0)) <= 0.5);
            previous = ticks;
        }
    }
}
