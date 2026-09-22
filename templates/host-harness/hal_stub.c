/* See hal_stub.h. Everything is fixed-size and bounds-checked so a misbehaving firmware call
 * shows up as a recorded overflow or a -1, never as memory corruption in the test binary. */
#include "hal_stub.h"

#include <string.h>

hal_stub_log_t hal_stub_log;

typedef struct {
    uint8_t data[HAL_STUB_QUEUE];
    size_t head, len;
} byte_queue_t;

static byte_queue_t spi_q;
static uint8_t spi_default[HAL_STUB_FRAME];
static size_t spi_default_len, spi_default_pos;
static struct {
    uint8_t addr;
    byte_queue_t q;
    int fail_left;
} i2c_dev[4];
static int n_i2c_dev;
static int spi_fail_left;
static uint32_t now_ms;

static bool q_push(byte_queue_t *q, const uint8_t *bytes, size_t n) {
    if (n > HAL_STUB_QUEUE - q->len) return false;
    for (size_t i = 0; i < n; i++) q->data[(q->head + q->len + i) % HAL_STUB_QUEUE] = bytes[i];
    q->len += n;
    return true;
}

static uint8_t q_pop(byte_queue_t *q) {
    if (q->len == 0) return 0xFF; /* an idle bus reads high */
    uint8_t b = q->data[q->head];
    q->head = (q->head + 1) % HAL_STUB_QUEUE;
    q->len--;
    return b;
}

static int i2c_slot(uint8_t addr, bool create) {
    for (int i = 0; i < n_i2c_dev; i++)
        if (i2c_dev[i].addr == addr) return i;
    if (!create || n_i2c_dev == (int)(sizeof i2c_dev / sizeof i2c_dev[0])) return -1;
    memset(&i2c_dev[n_i2c_dev], 0, sizeof i2c_dev[0]);
    i2c_dev[n_i2c_dev].addr = addr;
    return n_i2c_dev++;
}

void hal_stub_reset(void) {
    memset(&hal_stub_log, 0, sizeof hal_stub_log);
    memset(&spi_q, 0, sizeof spi_q);
    spi_default_len = spi_default_pos = 0;
    memset(i2c_dev, 0, sizeof i2c_dev);
    n_i2c_dev = 0;
    spi_fail_left = 0;
    now_ms = 0;
}

bool hal_stub_script_spi(const uint8_t *bytes, size_t n) { return q_push(&spi_q, bytes, n); }

bool hal_stub_script_i2c(uint8_t addr, const uint8_t *bytes, size_t n) {
    int s = i2c_slot(addr, true);
    return s >= 0 && q_push(&i2c_dev[s].q, bytes, n);
}

bool hal_stub_spi_default(const uint8_t *frame, size_t n) {
    if (n > HAL_STUB_FRAME) return false;
    if (n) memcpy(spi_default, frame, n);
    spi_default_len = n;
    spi_default_pos = 0;
    return true;
}

static uint8_t spi_pop(void) {
    if (spi_q.len) return q_pop(&spi_q);
    if (!spi_default_len) return 0xFF;
    uint8_t b = spi_default[spi_default_pos];
    spi_default_pos = (spi_default_pos + 1) % spi_default_len;
    return b;
}

void hal_stub_fail_spi(int count) { spi_fail_left = count; }

void hal_stub_fail_i2c(uint8_t addr, int count) {
    int s = i2c_slot(addr, true);
    if (s >= 0) i2c_dev[s].fail_left = count;
}

void hal_stub_advance_ms(uint32_t ms) { now_ms += ms; }

/* --- HAL surface --- */

int hal_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t n) {
    (void)tx;
    hal_stub_log.spi_transfers++;
    if (spi_fail_left > 0) {
        spi_fail_left--;
        hal_stub_log.spi_failures++;
        return -1;
    }
    for (size_t i = 0; i < n; i++) rx[i] = spi_pop();
    return 0;
}

int hal_i2c_read(uint8_t addr, uint8_t reg, uint8_t *buf, size_t n) {
    hal_stub_log.i2c_reads++;
    hal_stub_log.last_i2c_addr = addr;
    hal_stub_log.last_i2c_reg = reg;
    int s = i2c_slot(addr, false);
    if (s < 0 || i2c_dev[s].fail_left > 0) {
        if (s >= 0) i2c_dev[s].fail_left--;
        hal_stub_log.i2c_naks++;
        return -1;
    }
    for (size_t i = 0; i < n; i++) buf[i] = q_pop(&i2c_dev[s].q);
    return 0;
}

int hal_i2c_write(uint8_t addr, uint8_t reg, const uint8_t *buf, size_t n) {
    (void)buf;
    (void)n;
    hal_stub_log.i2c_writes++;
    hal_stub_log.last_i2c_addr = addr;
    hal_stub_log.last_i2c_reg = reg;
    return i2c_slot(addr, false) < 0 ? -1 : 0;
}

void hal_gpio_write(int pin, bool level) {
    hal_stub_log.gpio_writes++;
    hal_stub_log.last_gpio_pin = pin;
    hal_stub_log.last_gpio_level = level;
}

void hal_uart_write(const uint8_t *buf, size_t n) {
    if (n > HAL_STUB_UART_CAP - hal_stub_log.uart_len) {
        hal_stub_log.uart_overflow = true;
        n = HAL_STUB_UART_CAP - hal_stub_log.uart_len;
    }
    memcpy(hal_stub_log.uart + hal_stub_log.uart_len, buf, n);
    hal_stub_log.uart_len += n;
}

uint32_t hal_millis(void) { return now_ms; }
