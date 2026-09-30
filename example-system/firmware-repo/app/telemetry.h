/* Telemetry frame encode/decode (ICD section 3). Portable. */
#ifndef HUB_TELEMETRY_H
#define HUB_TELEMETRY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "config.h"

#define TELEMETRY_SYNC 0x7Eu

typedef struct {
    uint16_t seq;
    int16_t channel[HUB_CHANNELS];
    q16_t setpoint;
    uint8_t status;
} telemetry_t;

bool telemetry_encode(const telemetry_t *t, uint8_t out[HUB_TELEMETRY_LEN]);
bool telemetry_decode(const uint8_t *raw, size_t len, telemetry_t *out);

#endif
