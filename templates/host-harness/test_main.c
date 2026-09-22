/* Host tests over a firmware tree, with hardware replaced by hal_stub.c.
 *
 * As shipped it runs against example-system/src (the Makefile's default FW_SRC/FW_INC). To point it
 * at your tree: set FW_SRC/FW_INC, replace the #includes and the adapters in section 2, keep
 * sections 1 and 3. The adapters are the only place that knows both your HAL and the stub. */
#include <string.h>

#include "hal_stub.h"
#include "harness.h"

#include "node.h"    /* FW_INC */
#include "packet.h"

/* ---------- 1. Stub self-test: prove the fake hardware behaves before trusting it ---------- */
static void test_stub_scripts_and_records(void) {
    static const uint8_t temp_bytes[] = {0x09, 0xC4}; /* 2500 big-endian */
    CHECK(hal_stub_script_i2c(0x48, temp_bytes, 2));
    uint8_t buf[2] = {0, 0};
    CHECK_EQ_INT(hal_i2c_read(0x48, 0x00, buf, 2), 0);
    CHECK_EQ_INT((buf[0] << 8) | buf[1], 2500);
    CHECK_EQ_INT(hal_i2c_read(0x49, 0x00, buf, 2), -1); /* no such device: NAK */
    CHECK_EQ_INT(hal_stub_log.i2c_reads, 2);
    CHECK_EQ_INT(hal_stub_log.i2c_naks, 1);

    CHECK(!hal_stub_fail_spi(-1));                 /* a negative count is a test bug, not a no-op */
    CHECK(!hal_stub_fail_i2c(0x48, -1));
    CHECK(hal_stub_fail_spi(1));
    uint8_t tx[2] = {0x80, 0x00}, rx[2];
    CHECK_EQ_INT(hal_spi_transfer(tx, rx, 2), -1);
    CHECK_EQ_INT(hal_spi_transfer(tx, rx, 2), 0);  /* recovers after one failure */
    CHECK_EQ_INT(rx[0], 0xFF);                     /* nothing scripted: idle bus */

    hal_uart_write((const uint8_t *)"hi", 2);
    CHECK_EQ_INT(hal_stub_log.uart_len, 2);
    hal_stub_advance_ms(10);
    CHECK_EQ_INT(hal_millis(), 10);
}

/* Most I2C parts are configured with a write before the first read. The stub must ACK that write
 * for a registered device that has no read data queued yet, and NAK it for an empty address. */
static void test_stub_i2c_write_before_first_read(void) {
    static const uint8_t cfg[] = {0x60};
    CHECK(hal_stub_add_i2c(0x48));
    CHECK_EQ_INT(hal_i2c_write(0x48, 0x01, cfg, 1), 0);   /* registered, nothing scripted: ACK */
    CHECK_EQ_INT(hal_i2c_write(0x49, 0x01, cfg, 1), -1);  /* nothing at 0x49: NAK */
    CHECK_EQ_INT(hal_stub_log.i2c_writes, 2);
    CHECK_EQ_INT(hal_stub_log.i2c_naks, 1);
    CHECK_EQ_INT(hal_stub_log.last_i2c_addr, 0x49);
    CHECK_EQ_INT(hal_stub_log.last_i2c_reg, 0x01);

    uint8_t buf[2] = {0, 0};
    CHECK_EQ_INT(hal_i2c_read(0x48, 0x00, buf, 2), 0);   /* registered but no data: idle bus reads high */
    CHECK_EQ_INT(buf[0], 0xFF);

    CHECK(hal_stub_fail_i2c(0x48, 1));                      /* a fault NAKs the next transaction, write or read */
    CHECK_EQ_INT(hal_i2c_write(0x48, 0x01, cfg, 1), -1);
    CHECK_EQ_INT(hal_i2c_write(0x48, 0x01, cfg, 1), 0);
    CHECK_EQ_INT(hal_stub_log.i2c_naks, 2);

    CHECK(hal_stub_add_i2c(0x48));                          /* re-adding is idempotent, not a second slot */
    CHECK(hal_stub_add_i2c(0x10));
    CHECK(hal_stub_add_i2c(0x11));
    CHECK(hal_stub_add_i2c(0x12));
    CHECK(!hal_stub_add_i2c(0x13));                         /* 4 device slots: the fifth fails loudly */
}

/* ---------- 2. Adapters: the firmware's callback HAL -> the link-time stub ---------- */
/* On the target these would wrap the vendor SPI/I2C/GPIO drivers. */
#define IMU_FRAME_BYTES 8
#define TEMP_ADDR 0x48
#define IMU_RESET_PIN 7

static bool imu_read_via_spi(void *ctx, imu_sample_t *out) {
    (void)ctx;
    uint8_t tx[IMU_FRAME_BYTES] = {0x80}, rx[IMU_FRAME_BYTES];
    if (hal_spi_transfer(tx, rx, IMU_FRAME_BYTES) != 0) return false;
    out->acc_x = (int16_t)((rx[0] << 8) | rx[1]);
    out->acc_y = (int16_t)((rx[2] << 8) | rx[3]);
    out->acc_z = (int16_t)((rx[4] << 8) | rx[5]);
    out->gyro_z = (int16_t)((rx[6] << 8) | rx[7]);
    return true;
}

static void imu_reinit_via_gpio(void *ctx) {
    (void)ctx;
    hal_gpio_write(IMU_RESET_PIN, false);
    hal_gpio_write(IMU_RESET_PIN, true);
}

static int16_t temp_read_via_i2c(void *ctx) {
    (void)ctx;
    uint8_t b[2];
    if (hal_i2c_read(TEMP_ADDR, 0x00, b, 2) != 0) return TEMP_MAX_CC + 1; /* out of range -> fault */
    return (int16_t)((b[0] << 8) | b[1]);
}

static void imu_answers(int16_t acc_z) { /* the IMU returns this frame on every poll */
    uint8_t f[IMU_FRAME_BYTES] = {0, 0, 0, 0, (uint8_t)(acc_z >> 8), (uint8_t)acc_z, 0, 0};
    CHECK(hal_stub_spi_default(f, IMU_FRAME_BYTES));
}

static void script_temp(int reads, int16_t cc) {
    uint8_t b[2] = {(uint8_t)(cc >> 8), (uint8_t)cc};
    for (int i = 0; i < reads; i++) CHECK(hal_stub_script_i2c(TEMP_ADDR, b, 2));
}

/* ---------- 3. Firmware behaviour through the stub ---------- */
static int run_ticks(node_t *n, int ticks) { /* returns packets emitted; copies each to the "UART" */
    uint8_t out[PACKET_LEN];
    int packets = 0;
    for (int i = 0; i < ticks; i++) {
        if (node_step(n, out)) {
            hal_uart_write(out, PACKET_LEN);
            packets++;
        }
        hal_stub_advance_ms(10);
    }
    return packets;
}

static void test_one_second_produces_one_valid_packet(void) { /* SN-REQ-001, 004, 005 */
    imu_answers(8192);
    script_temp(1, 2350);
    node_t n;
    node_init(&n, imu_read_via_spi, imu_reinit_via_gpio, temp_read_via_i2c, NULL);
    CHECK_EQ_INT(run_ticks(&n, 100), 1);
    CHECK_EQ_INT(hal_stub_log.spi_transfers, 100);
    CHECK_EQ_INT(hal_stub_log.i2c_reads, 1);
    CHECK_EQ_INT(hal_stub_log.uart_len, PACKET_LEN);
    packet_t p;
    CHECK(packet_parse(hal_stub_log.uart, PACKET_LEN, &p));
    CHECK_EQ_INT(p.acc_z, 8192);
    CHECK_EQ_INT(p.temp_cc, 2350);
    CHECK_EQ_INT(p.flags, 0);
    CHECK_EQ_INT(hal_millis(), 1000);
}

static void test_spi_dropout_triggers_imu_reinit(void) { /* SN-REQ-008 */
    CHECK(hal_stub_fail_spi(IMU_TIMEOUT_SAMPLES));
    imu_answers(8192);
    script_temp(1, 2350);
    node_t n;
    node_init(&n, imu_read_via_spi, imu_reinit_via_gpio, temp_read_via_i2c, NULL);
    run_ticks(&n, 100);
    CHECK_EQ_INT(n.imu_reinit_count, 1);
    CHECK_EQ_INT(hal_stub_log.gpio_writes, 2); /* reset pin low then high, once */
    CHECK_EQ_INT(hal_stub_log.last_gpio_pin, IMU_RESET_PIN);
    CHECK(hal_stub_log.last_gpio_level);
    packet_t p;
    CHECK(packet_parse(hal_stub_log.uart, PACKET_LEN, &p));
    CHECK(p.flags & FLAG_IMU_REINIT);
}

static void test_i2c_nak_is_reported_as_temp_fault(void) { /* SN-REQ-007 */
    imu_answers(8192);
    script_temp(1, 2500);
    node_t n;
    node_init(&n, imu_read_via_spi, imu_reinit_via_gpio, temp_read_via_i2c, NULL);
    run_ticks(&n, 100);
    CHECK(hal_stub_fail_i2c(TEMP_ADDR, 1)); /* second read NAKs */
    run_ticks(&n, 100);
    packet_t p;
    CHECK(packet_parse(hal_stub_log.uart + PACKET_LEN, PACKET_LEN, &p));
    CHECK(p.flags & FLAG_FAULT);
    CHECK_EQ_INT(p.temp_cc, 2500); /* last good value is held */
}

int main(void) {
    RUN(test_stub_scripts_and_records);
    RUN(test_stub_i2c_write_before_first_read);
    RUN(test_one_second_produces_one_valid_packet);
    RUN(test_spi_dropout_triggers_imu_reinit);
    RUN(test_i2c_nak_is_reported_as_temp_fault);
    return harness_report();
}
