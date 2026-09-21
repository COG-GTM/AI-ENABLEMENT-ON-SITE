#include "node.h"

void node_init(node_t *n, imu_read_fn imu, imu_reinit_fn reinit, temp_read_fn temp, void *ctx) {
    n->read_imu = imu;
    n->reinit_imu = reinit;
    n->read_temp = temp;
    n->ctx = ctx;
    for (int i = 0; i < 4; i++) filter_init(&n->filt[i]);
    n->seq = 0;
    n->tick = 0;
    n->fault = false;
    n->imu_reinit = false;
    n->imu_misses = 0;
    n->imu_reinit_count = 0;
    n->last_temp_cc = 2500;
    n->filtered = (imu_sample_t){0, 0, 0, 0};
}

static void sample_imu(node_t *n) {
    imu_sample_t raw;
    if (!n->read_imu(n->ctx, &raw)) {
        if (++n->imu_misses >= IMU_TIMEOUT_SAMPLES) { /* SN-REQ-008 */
            n->fault = true;
            n->imu_reinit = true;
            n->imu_reinit_count++;
            n->imu_misses = 0;
            for (int i = 0; i < 4; i++) filter_reset(&n->filt[i]);
            if (n->reinit_imu) n->reinit_imu(n->ctx);
        }
        return;
    }
    n->imu_misses = 0;
    n->filtered.acc_x = filter_update(&n->filt[0], raw.acc_x);
    n->filtered.acc_y = filter_update(&n->filt[1], raw.acc_y);
    n->filtered.acc_z = filter_update(&n->filt[2], raw.acc_z);
    n->filtered.gyro_z = filter_update(&n->filt[3], raw.gyro_z);
}

static void sample_temp(node_t *n) {
    int16_t t = n->read_temp(n->ctx);
    if (t >= TEMP_MIN_CC && t <= TEMP_MAX_CC) {
        n->last_temp_cc = t;
    } else { /* SN-REQ-007 */
        n->fault = true;
    }
}

static void emit(node_t *n, uint8_t out[PACKET_LEN]) {
    packet_t p = {
        .seq = n->seq,
        .acc_x = n->filtered.acc_x,
        .acc_y = n->filtered.acc_y,
        .acc_z = n->filtered.acc_z,
        .gyro_z = n->filtered.gyro_z,
        .temp_cc = n->last_temp_cc,
        .flags = (uint8_t)((n->fault ? FLAG_FAULT : 0) | (n->imu_reinit ? FLAG_IMU_REINIT : 0)),
    };
    (void)packet_build(&p, out);
    n->seq = packet_next_seq(n->seq);
    n->fault = false;
    n->imu_reinit = false;
}

bool node_step(node_t *n, uint8_t out[PACKET_LEN]) {
    sample_imu(n);
    if (n->tick % (IMU_RATE_HZ / TEMP_RATE_HZ) == 0) sample_temp(n);
    bool emitted = false;
    if ((n->tick + 1) % (IMU_RATE_HZ / UPLINK_RATE_HZ) == 0) { /* end of each 1 s window */
        emit(n, out);
        emitted = true;
    }
    n->tick++;
    return emitted;
}
