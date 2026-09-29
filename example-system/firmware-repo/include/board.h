/* Register map for the target MCU. Everything in here is target-only: the addresses do not exist on a host. */
#ifndef HUB_BOARD_H
#define HUB_BOARD_H

#include <stdint.h>

#define PERIPH_BASE   0x40000000u
#define GPIOA_BASE    (PERIPH_BASE + 0x00020000u)
#define SPI1_BASE     (PERIPH_BASE + 0x00013000u)
#define ADC1_BASE     (PERIPH_BASE + 0x00012000u)

#define REG32(addr)   (*(volatile uint32_t *)(addr))
#define GPIOA_ODR     REG32(GPIOA_BASE + 0x14u)
#define SPI1_DR       REG32(SPI1_BASE + 0x0Cu)
#define SPI1_SR       REG32(SPI1_BASE + 0x08u)
#define ADC1_DR       REG32(ADC1_BASE + 0x4Cu)
#define SPI_SR_RXNE   (1u << 0)
#define SPI_SR_TXE    (1u << 1)

#endif
