/* Sensor-node control loop (SN-REQ-001..010). Twin: sim/sensor_node/node.py
 * Hardware access goes through function pointers so the loop runs on a host. */
#ifndef SN_NODE_H
#define SN_NODE_H

#include <stdbool.h>
#include <stdint.h>

#include "filter.h"
#include "packet.h"

#define IMU_RATE_HZ 100
#define TEMP_RATE_HZ 1
#define UPLINK_RATE_HZ 1
#define IMU_TIMEOUT_SAMPLES 5
#define TEMP_MIN_CC (-4000)
#define TEMP_MAX_CC 8500

typedef struct {
    int16_t acc_x, acc_y, acc_z, gyro_z;
} imu_sample_t;

/* Return false when the IMU does not respond. */
typedef bool (*imu_read_fn)(void *ctx, imu_sample_t *out);
/* Re-initialise the IMU after a timeout (SN-REQ-008). May be NULL. */
typedef void (*imu_reinit_fn)(void *ctx);
typedef int16_t (*temp_read_fn)(void *ctx);

typedef struct {
    imu_read_fn read_imu;
    imu_reinit_fn reinit_imu;
    temp_read_fn read_temp;
    void *ctx;
    filter_t filt[4];
    uint16_t seq;
    uint32_t tick;
    bool fault, imu_reinit;
    uint8_t imu_misses;
    uint32_t imu_reinit_count;
    int16_t last_temp_cc;
    imu_sample_t filtered;
} node_t;

void node_init(node_t *n, imu_read_fn imu, imu_reinit_fn reinit, temp_read_fn temp, void *ctx);
/* One 10 ms tick. Returns true and fills `out` once per second. */
bool node_step(node_t *n, uint8_t out[PACKET_LEN]);

#endif
