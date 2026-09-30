/* Polled SPI over the register map, with GPIO chip select and a busy-wait timeout. Target-only. */
#include "spi_driver.h"

#include "board.h"
#include "hal_gpio.h"

#define SPI_CS_PIN   4
#define SPI_TIMEOUT  10000u

static volatile uint32_t spi_errors;

void spi_driver_init(void)
{
    spi_errors = 0;
    hal_gpio_write(SPI_CS_PIN, true);
}

static int wait_flag(uint32_t flag)
{
    uint32_t spins = SPI_TIMEOUT;
    while (!(SPI1_SR & flag)) {
        if (--spins == 0) {
            spi_errors++;
            return -1;
        }
    }
    return 0;
}

int spi_transfer(const uint8_t *tx, uint8_t *rx, size_t n)
{
    hal_gpio_write(SPI_CS_PIN, false);
    for (size_t i = 0; i < n; i++) {
        if (wait_flag(SPI_SR_TXE) < 0) {
            hal_gpio_write(SPI_CS_PIN, true);
            return -1;
        }
        SPI1_DR = tx[i];
        if (wait_flag(SPI_SR_RXNE) < 0) {
            hal_gpio_write(SPI_CS_PIN, true);
            return -1;
        }
        rx[i] = (uint8_t)SPI1_DR;
    }
    hal_gpio_write(SPI_CS_PIN, true);
    return 0;
}
