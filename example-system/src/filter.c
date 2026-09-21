#include "filter.h"

void filter_init(filter_t *f) { filter_reset(f); }

void filter_reset(filter_t *f) {
    for (uint8_t i = 0; i < FILTER_WINDOW; i++) f->buf[i] = 0;
    f->head = 0;
    f->count = 0;
}

int16_t filter_update(filter_t *f, int16_t sample) {
    f->buf[f->head] = sample;
    f->head = (uint8_t)((f->head + 1) % FILTER_WINDOW);
    if (f->count < FILTER_WINDOW) f->count++;
    int32_t sum = 0;
    for (uint8_t i = 0; i < f->count; i++) sum += f->buf[i];
    return (int16_t)(sum / f->count); /* C division truncates toward zero */
}
