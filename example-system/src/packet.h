/* Uplink packet, ICD section 4 (SN-REQ-004..006, 009). Twin: sim/sensor_node/packet.py */
#ifndef SN_PACKET_H
#define SN_PACKET_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PACKET_LEN 16
#define PACKET_SYNC 0xA5
#define FLAG_FAULT 0x01
#define FLAG_IMU_REINIT 0x02

typedef struct {
    uint16_t seq;
    int16_t acc_x, acc_y, acc_z, gyro_z;
    int16_t temp_cc; /* centi-degrees C */
    uint8_t flags;
} packet_t;

uint16_t crc16_ccitt_false(const uint8_t *data, size_t len);
/* Returns false if flags use reserved bits. */
bool packet_build(const packet_t *p, uint8_t out[PACKET_LEN]);
/* Returns false on bad length/sync/CRC. */
bool packet_parse(const uint8_t *raw, size_t len, packet_t *out);
static inline uint16_t packet_next_seq(uint16_t seq) { return (uint16_t)(seq + 1u); }

#endif
