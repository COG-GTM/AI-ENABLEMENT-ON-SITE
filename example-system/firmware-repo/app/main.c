/* Entry point: bring the board up, then run the scheduler forever. Target-only glue around portable logic. */
#include "board.h"
#include "config.h"
#include "hal_gpio.h"
#include "scheduler.h"
#include "spi_driver.h"
#include "system_init.h"
#include "telemetry.h"

static scheduler_t sched;

int main(void)
{
    system_init();
    hal_gpio_init();
    spi_driver_init();
    scheduler_init(&sched, HUB_TICK_HZ);
    for (;;) {
        __asm volatile("wfi");
        scheduler_run_pending(&sched);
    }
    return 0;
}
