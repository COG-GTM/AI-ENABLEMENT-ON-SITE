/* Reset vector and the vector table. Linker symbols and the Cortex-M reset sequence: nothing here is host code. */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
extern int main(void);
extern void ADC_IRQHandler(void);

void Reset_Handler(void)
{
    uint32_t *src = &_sidata, *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }
    for (dst = &_sbss; dst < &_ebss;) {
        *dst++ = 0;
    }
    __asm volatile("cpsie i");
    (void)main();
    for (;;) {
    }
}

void Default_Handler(void)
{
    for (;;) {
    }
}

__attribute__((section(".isr_vector"))) const void *vector_table[] = {
    &_estack, Reset_Handler, Default_Handler, Default_Handler, ADC_IRQHandler,
};
