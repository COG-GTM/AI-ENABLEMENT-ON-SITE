/* SPI transfer with chip select. The logic above it only sees spi_transfer(). */
#ifndef HUB_SPI_DRIVER_H
#define HUB_SPI_DRIVER_H

#include <stddef.h>
#include <stdint.h>

void spi_driver_init(void);
int  spi_transfer(const uint8_t *tx, uint8_t *rx, size_t n);   /* 0 ok, -1 timeout */

#endif
