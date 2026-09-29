/* GPIO access. Target-only implementation; the prototypes are the seam a host stub replaces. */
#ifndef HUB_HAL_GPIO_H
#define HUB_HAL_GPIO_H

#include <stdbool.h>

void hal_gpio_init(void);
void hal_gpio_write(int pin, bool level);
bool hal_gpio_read(int pin);

#endif
