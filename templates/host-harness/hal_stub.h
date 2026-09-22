/* Host stand-in for a firmware hardware abstraction layer (HAL).
 *
 * Two ways firmware reaches hardware, and how this file covers each:
 *   1. Link-time: the firmware calls hal_spi_transfer(), hal_i2c_read(), ... directly. On the target
 *      those live in the vendor BSP; on the host, link THIS file instead. Rename the functions below
 *      to match your tree (keep the record/script API).
 *   2. Callbacks: the firmware takes function pointers (example-system/src/node.h does this). Point
 *      them at small adapters that call the functions below; test_main.c shows that.
 *
 * Inputs are scripted (what the "device" will answer), outputs are recorded (what the firmware sent),
 * time is a counter you advance by hand. No threads, no real waiting. */
#ifndef HOST_HAL_STUB_H
#define HOST_HAL_STUB_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HAL_STUB_QUEUE 1024  /* scripted bytes per bus */
#define HAL_STUB_FRAME 64    /* max bytes in a repeating default frame */
#define HAL_STUB_UART_CAP 1024

/* --- the HAL surface the firmware links against (rename to match your tree) --- */
int      hal_spi_transfer(const uint8_t *tx, uint8_t *rx, size_t n);          /* 0 ok, -1 no device */
int      hal_i2c_read(uint8_t addr, uint8_t reg, uint8_t *buf, size_t n);     /* 0 ok, -1 NAK */
int      hal_i2c_write(uint8_t addr, uint8_t reg, const uint8_t *buf, size_t n);
void     hal_gpio_write(int pin, bool level);
void     hal_uart_write(const uint8_t *buf, size_t n);
uint32_t hal_millis(void);

/* --- test-side control --- */
typedef struct {
    int spi_transfers, spi_failures, i2c_reads, i2c_writes, i2c_naks, gpio_writes;
    int last_gpio_pin;
    bool last_gpio_level;
    uint8_t last_i2c_addr, last_i2c_reg;
    uint8_t uart[HAL_STUB_UART_CAP];
    size_t uart_len;
    bool uart_overflow;
} hal_stub_log_t;

extern hal_stub_log_t hal_stub_log;

void hal_stub_reset(void);
/* Queue bytes the bus will answer with, in order. Returns false if the queue is full. */
bool hal_stub_script_spi(const uint8_t *bytes, size_t n);
bool hal_stub_script_i2c(uint8_t addr, const uint8_t *bytes, size_t n);
/* Frame the SPI device answers with, cyclically, once the scripted queue is empty (for firmware
 * that polls a sensor thousands of times per test). n == 0 clears it; idle bus reads 0xFF. */
bool hal_stub_spi_default(const uint8_t *frame, size_t n);
/* Make the next `count` SPI transfers (or I2C reads of `addr`) fail, then recover. Returns false
 * for a negative count or when no I2C device slot is free, so a bad test setup fails loudly. */
bool hal_stub_fail_spi(int count);
bool hal_stub_fail_i2c(uint8_t addr, int count);
void hal_stub_advance_ms(uint32_t ms);

#endif
