/* ADC end-of-conversion interrupt: despike with the median filter and hand samples to the telemetry task. */
#include <stdint.h>

#include "board.h"
#include "config.h"
#include "median.h"

static median_t despike[HUB_CHANNELS];
static volatile int16_t latest[HUB_CHANNELS];
static volatile uint8_t channel_idx;

void adc_isr_init(void)
{
    for (uint8_t i = 0; i < HUB_CHANNELS; i++) {
        median_init(&despike[i]);
        latest[i] = 0;
    }
    channel_idx = 0;
}

int16_t adc_latest(uint8_t channel)
{
    return latest[channel % HUB_CHANNELS];
}

void ADC_IRQHandler(void)
{
    int16_t raw = (int16_t)(ADC1_DR & 0x0FFFu);
    latest[channel_idx] = median_update(&despike[channel_idx], raw);
    channel_idx = (uint8_t)((channel_idx + 1u) % HUB_CHANNELS);
    NVIC_ClearPendingIRQ(ADC_IRQn);
}
