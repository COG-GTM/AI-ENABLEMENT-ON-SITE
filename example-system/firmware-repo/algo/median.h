/* Median-of-N filter for ADC despiking (REQ-FILT-002). Portable. */
#ifndef HUB_MEDIAN_H
#define HUB_MEDIAN_H

#include <stddef.h>
#include <stdint.h>

#define MEDIAN_WINDOW 5u

typedef struct {
    int16_t buf[MEDIAN_WINDOW];
    uint8_t head;
    uint8_t count;
} median_t;

void    median_init(median_t *m);
int16_t median_update(median_t *m, int16_t sample);
int16_t median_of(const int16_t *v, size_t n);

#endif
