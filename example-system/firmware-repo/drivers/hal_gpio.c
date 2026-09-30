/* GPIO through memory-mapped registers. Target-only: REG32 dereferences fixed addresses. */
#include "hal_gpio.h"

#include "board.h"

void hal_gpio_init(void)
{
    GPIOA_ODR = 0u;
}

void hal_gpio_write(int pin, bool level)
{
    if (level) {
        GPIOA_ODR |= (1u << pin);
    } else {
        GPIOA_ODR &= ~(1u << pin);
    }
}

bool hal_gpio_read(int pin)
{
    return (GPIOA_ODR >> pin) & 1u;
}
