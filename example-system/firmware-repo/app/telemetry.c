/* Telemetry frame encode/decode (REQ-TLM-001..005). Uses the vendor CRC; otherwise pure C. */
#include "telemetry.h"

#include <string.h>

#include "crc16_vendor.h"

static void put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v >> 8);
    p[1] = (uint8_t)v;
}

static uint16_t get_u16(const uint8_t *p)
{
    return (uint16_t)((p[0] << 8) | p[1]);
}

bool telemetry_encode(const telemetry_t *t, uint8_t out[HUB_TELEMETRY_LEN])
{
    if (t->status & 0xF0u) {
        return false;   /* reserved status bits */
    }
    memset(out, 0, HUB_TELEMETRY_LEN);
    out[0] = TELEMETRY_SYNC;
    put_u16(&out[1], t->seq);
    for (size_t i = 0; i < HUB_CHANNELS; i++) {
        put_u16(&out[3 + 2 * i], (uint16_t)t->channel[i]);
    }
    out[11] = (uint8_t)(t->setpoint >> 24);
    out[12] = (uint8_t)(t->setpoint >> 16);
    out[13] = (uint8_t)(t->setpoint >> 8);
    out[14] = (uint8_t)t->setpoint;
    out[15] = t->status;
    put_u16(&out[HUB_TELEMETRY_LEN - 2], crc16_vendor(out, HUB_TELEMETRY_LEN - 2));
    return true;
}

bool telemetry_decode(const uint8_t *raw, size_t len, telemetry_t *out)
{
    if (len != HUB_TELEMETRY_LEN || raw[0] != TELEMETRY_SYNC) {
        return false;
    }
    if (get_u16(&raw[HUB_TELEMETRY_LEN - 2]) != crc16_vendor(raw, HUB_TELEMETRY_LEN - 2)) {
        return false;
    }
    out->seq = get_u16(&raw[1]);
    for (size_t i = 0; i < HUB_CHANNELS; i++) {
        out->channel[i] = (int16_t)get_u16(&raw[3 + 2 * i]);
    }
    out->setpoint = (q16_t)(((uint32_t)raw[11] << 24) | ((uint32_t)raw[12] << 16) | ((uint32_t)raw[13] << 8) | raw[14]);
    out->status = raw[15];
    return true;
}
