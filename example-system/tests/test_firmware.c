/* Host-side C tests. Build and run with `make test` from example-system/.
 * Same requirement coverage as the Python tests so both twins stay in sync. */
#include <stdio.h>
#include <string.h>

#include "../src/filter.h"
#include "../src/node.h"
#include "../src/packet.h"

static int failures = 0;
#define CHECK(cond)                                                              \
    do {                                                                         \
        if (!(cond)) {                                                           \
            failures++;                                                          \
            printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond);                \
        }                                                                        \
    } while (0)

static void test_crc_check_value(void) {
    CHECK(crc16_ccitt_false((const uint8_t *)"123456789", 9) == 0x29B1);
}

static void test_known_vector(void) { /* SN-REQ-005, SN-REQ-006 */
    packet_t p = {.seq = 1, .acc_x = 0, .acc_y = 0, .acc_z = 8192, .gyro_z = 0, .temp_cc = 2350, .flags = 0};
    uint8_t out[PACKET_LEN];
    CHECK(packet_build(&p, out));
    const uint8_t expect[PACKET_LEN] = {0xa5, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00,
                                        0x20, 0x00, 0x00, 0x00, 0x09, 0x2e, 0x77, 0x6a};
    CHECK(memcmp(out, expect, PACKET_LEN) == 0);
}

static void test_round_trip_and_corruption(void) { /* SN-REQ-004 */
    packet_t p = {.seq = 1234, .acc_x = -100, .acc_y = 55, .acc_z = 8000, .gyro_z = -3, .temp_cc = -1250, .flags = 1};
    uint8_t out[PACKET_LEN];
    packet_t back;
    CHECK(packet_build(&p, out));
    CHECK(packet_parse(out, PACKET_LEN, &back));
    CHECK(back.seq == 1234 && back.acc_x == -100 && back.temp_cc == -1250 && back.flags == 1);
    out[5] ^= 1;
    CHECK(!packet_parse(out, PACKET_LEN, &back));
    p.flags = 0x04;
    CHECK(!packet_build(&p, out));
}

static void test_seq_wraps(void) { CHECK(packet_next_seq(65535) == 0); } /* SN-REQ-009 */

static void test_filter(void) { /* SN-REQ-003 */
    filter_t f;
    filter_init(&f);
    CHECK(filter_update(&f, 100) == 100);
    CHECK(filter_update(&f, 200) == 150);
    CHECK(filter_update(&f, 300) == 200);
    CHECK(filter_update(&f, 400) == 250);
    CHECK(filter_update(&f, 800) == (200 + 300 + 400 + 800) / 4);
    filter_reset(&f);
    filter_update(&f, -1);
    filter_update(&f, -1);
    CHECK(filter_update(&f, -1) == -1);
    CHECK(filter_update(&f, 0) == 0);
}

/* --- node tests with injected hardware --- */
typedef struct {
    int imu_calls, temp_calls, imu_fail_first_n;
    const int16_t *temps;
    int ntemps;
} fake_hw_t;

static bool fake_imu(void *ctx, imu_sample_t *out) {
    fake_hw_t *hw = ctx;
    hw->imu_calls++;
    if (hw->imu_calls <= hw->imu_fail_first_n) return false;
    *out = (imu_sample_t){0, 0, 8192, 0};
    return true;
}

static int16_t fake_temp(void *ctx) {
    fake_hw_t *hw = ctx;
    int i = hw->temp_calls < hw->ntemps ? hw->temp_calls : hw->ntemps - 1;
    hw->temp_calls++;
    return hw->temps[i];
}

static void test_timing(void) { /* SN-REQ-001, 002, 004 */
    static const int16_t temps[] = {2500};
    fake_hw_t hw = {0, 0, 0, temps, 1};
    node_t n;
    node_init(&n, fake_imu, fake_temp, &hw);
    uint8_t out[PACKET_LEN];
    int packets = 0;
    uint16_t last_seq = 0;
    for (int i = 0; i < 1000; i++) {
        if (node_step(&n, out)) {
            packet_t p;
            CHECK(packet_parse(out, PACKET_LEN, &p));
            last_seq = p.seq;
            packets++;
        }
    }
    CHECK(packets == 10);
    CHECK(last_seq == 9);
    CHECK(hw.temp_calls == 10);
}

static void test_temp_fault(void) { /* SN-REQ-007 */
    static const int16_t temps[] = {2500, 9000, 2600};
    fake_hw_t hw = {0, 0, 0, temps, 3};
    node_t n;
    node_init(&n, fake_imu, fake_temp, &hw);
    uint8_t out[PACKET_LEN];
    packet_t p[3];
    int k = 0;
    for (int i = 0; i < 300 && k < 3; i++) {
        if (node_step(&n, out)) CHECK(packet_parse(out, PACKET_LEN, &p[k++]));
    }
    CHECK(p[0].temp_cc == 2500 && p[0].flags == 0);
    CHECK(p[1].temp_cc == 2500 && (p[1].flags & FLAG_FAULT));
    CHECK(p[2].temp_cc == 2600 && p[2].flags == 0);
}

static void test_imu_timeout(void) { /* SN-REQ-008 */
    static const int16_t temps[] = {2500};
    fake_hw_t hw = {0, 0, IMU_TIMEOUT_SAMPLES, temps, 1};
    node_t n;
    node_init(&n, fake_imu, fake_temp, &hw);
    uint8_t out[PACKET_LEN];
    packet_t p;
    for (int i = 0; i < 100; i++) {
        if (node_step(&n, out)) CHECK(packet_parse(out, PACKET_LEN, &p));
    }
    CHECK((p.flags & FLAG_FAULT) && (p.flags & FLAG_IMU_REINIT));
    CHECK(n.imu_reinit_count == 1);

    fake_hw_t hw2 = {0, 0, IMU_TIMEOUT_SAMPLES - 1, temps, 1};
    node_init(&n, fake_imu, fake_temp, &hw2);
    for (int i = 0; i < 100; i++) {
        if (node_step(&n, out)) CHECK(packet_parse(out, PACKET_LEN, &p));
    }
    CHECK(p.flags == 0);
}

int main(void) {
    test_crc_check_value();
    test_known_vector();
    test_round_trip_and_corruption();
    test_seq_wraps();
    test_filter();
    test_timing();
    test_temp_fault();
    test_imu_timeout();
    if (failures) {
        printf("%d check(s) failed\n", failures);
        return 1;
    }
    printf("C tests: all checks passed\n");
    return 0;
}
