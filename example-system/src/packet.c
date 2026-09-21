#include "packet.h"

uint16_t crc16_ccitt_false(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)(data[i] << 8);
        for (int b = 0; b < 8; b++) {
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static void put_u16(uint8_t *dst, uint16_t v) {
    dst[0] = (uint8_t)(v >> 8);
    dst[1] = (uint8_t)(v & 0xFF);
}

static uint16_t get_u16(const uint8_t *src) { return (uint16_t)((src[0] << 8) | src[1]); }

bool packet_build(const packet_t *p, uint8_t out[PACKET_LEN]) {
    if (p->flags & (uint8_t)~(FLAG_FAULT | FLAG_IMU_REINIT)) return false;
    out[0] = PACKET_SYNC;
    out[1] = p->flags;
    put_u16(&out[2], p->seq);
    put_u16(&out[4], (uint16_t)p->acc_x);
    put_u16(&out[6], (uint16_t)p->acc_y);
    put_u16(&out[8], (uint16_t)p->acc_z);
    put_u16(&out[10], (uint16_t)p->gyro_z);
    put_u16(&out[12], (uint16_t)p->temp_cc);
    put_u16(&out[14], crc16_ccitt_false(out, 14));
    return true;
}

bool packet_parse(const uint8_t *raw, size_t len, packet_t *out) {
    if (len != PACKET_LEN || raw[0] != PACKET_SYNC) return false;
    if (get_u16(&raw[14]) != crc16_ccitt_false(raw, 14)) return false;
    out->flags = raw[1];
    out->seq = get_u16(&raw[2]);
    out->acc_x = (int16_t)get_u16(&raw[4]);
    out->acc_y = (int16_t)get_u16(&raw[6]);
    out->acc_z = (int16_t)get_u16(&raw[8]);
    out->gyro_z = (int16_t)get_u16(&raw[10]);
    out->temp_cc = (int16_t)get_u16(&raw[12]);
    return true;
}
