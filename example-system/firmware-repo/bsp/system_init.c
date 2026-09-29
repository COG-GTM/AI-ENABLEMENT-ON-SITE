/* Clock and interrupt setup. Conditional compilation per board; every branch is target-only. */
#include "system_init.h"

#include "board.h"

#if defined(BOARD_REV_C)
#  define SYSCLK_HZ 168000000u
#elif defined(BOARD_REV_B)
#  define SYSCLK_HZ 84000000u
#else
#  error "unknown board"
#endif

void system_init(void)
{
    SystemCoreClockUpdate();
    HAL_Init();
    NVIC_SetPriority(ADC_IRQn, 2);
    NVIC_EnableIRQ(ADC_IRQn);
    __enable_irq();
}
