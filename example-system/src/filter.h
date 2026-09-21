/* Moving-average filter (SN-REQ-003). Twin: sim/sensor_node/filter.py */
#ifndef SN_FILTER_H
#define SN_FILTER_H

#include <stdint.h>

#define FILTER_WINDOW 4

typedef struct {
    int16_t buf[FILTER_WINDOW];
    uint8_t head;
    uint8_t count;
} filter_t;

void filter_init(filter_t *f);
void filter_reset(filter_t *f);
int16_t filter_update(filter_t *f, int16_t sample);

#endif
