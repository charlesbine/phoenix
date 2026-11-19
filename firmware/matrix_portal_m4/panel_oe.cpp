#include <Arduino.h>
#include "panel_color.h"

#if !defined(ADAFRUIT_MATRIXPORTAL_M4_EXPRESS)
#error This OE driver targets the Matrix Portal M4.
#endif

static volatile uint8_t brightness = 0;

void beginPanelOE() {
    // D16 is PB12. Its G mux connects TCC0/WO[0] directly to active-low OE.
    // Protomatter's TC4 and this one-shot both use the Arduino 48 MHz GCLK1.
    MCLK->APBBMASK.reg |= MCLK_APBBMASK_TCC0;
    GCLK->PCHCTRL[TCC0_GCLK_ID].reg = GCLK_PCHCTRL_GEN_GCLK1 | GCLK_PCHCTRL_CHEN;
    while (!GCLK->PCHCTRL[TCC0_GCLK_ID].bit.CHEN) {}

    TCC0->CTRLA.reg = TCC_CTRLA_SWRST;
    while (TCC0->SYNCBUSY.bit.SWRST) {}
    TCC0->WAVE.reg = TCC_WAVE_WAVEGEN_NPWM | TCC_WAVE_POL0;
    while (TCC0->SYNCBUSY.bit.WAVE) {}
    TCC0->DRVCTRL.reg = TCC_DRVCTRL_NRE0 | TCC_DRVCTRL_NRV0;
    TCC0->CTRLBSET.reg = TCC_CTRLBSET_ONESHOT;
    while (TCC0->SYNCBUSY.bit.CTRLB) {}
    TCC0->CTRLA.reg = TCC_CTRLA_ENABLE;
    while (TCC0->SYNCBUSY.bit.ENABLE) {}
    TCC0->CTRLBSET.reg = TCC_CTRLBSET_CMD_STOP;
    while (TCC0->SYNCBUSY.bit.CTRLB || !TCC0->STATUS.bit.STOP) {}

    PortGroup &port = PORT->Group[PORTB];
    port.PMUX[12 / 2].bit.PMUXE = MUX_PB12G_TCC0_WO0;
    port.PINCFG[12].bit.PMUXEN = 1;
}

void setPanelBrightness(uint8_t value) {
    brightness = value;
}

// Called by the patched Protomatter row ISR after the latch and row address
// settle. The counter finishes independently while the ISR shifts RGB data.
extern "C" void phoenixOePulse(uint32_t period) {
    const uint8_t level = brightness;
    if (!level) return;
    const uint32_t ticks = panel::oePulseTicks(period, level);
    if (!ticks) return;

    TCC0->PER.reg = period - 1;
    TCC0->CC[0].reg = ticks;
    while (TCC0->SYNCBUSY.reg & (TCC_SYNCBUSY_PER | TCC_SYNCBUSY_CC0)) {}
    TCC0->CTRLBSET.reg = TCC_CTRLBSET_CMD_RETRIGGER;
    while (TCC0->SYNCBUSY.bit.CTRLB) {}
}
