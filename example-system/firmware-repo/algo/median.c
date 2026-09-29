/* Median-of-N filter. Insertion sort on a copy of the window: bounded, no allocation. */
#include "median.h"

void median_init(median_t *m)
{
    m->head = 0;
    m->count = 0;
    for (size_t i = 0; i < MEDIAN_WINDOW; i++) {
        m->buf[i] = 0;
    }
}

int16_t median_of(const int16_t *v, size_t n)
{
    int16_t tmp[MEDIAN_WINDOW];
    if (n == 0 || n > MEDIAN_WINDOW) {
        return 0;
    }
    for (size_t i = 0; i < n; i++) {
        tmp[i] = v[i];
        for (size_t j = i; j > 0 && tmp[j - 1] > tmp[j]; j--) {
            int16_t t = tmp[j];
            tmp[j] = tmp[j - 1];
            tmp[j - 1] = t;
        }
    }
    return tmp[n / 2];
}

int16_t median_update(median_t *m, int16_t sample)
{
    m->buf[m->head] = sample;
    m->head = (uint8_t)((m->head + 1u) % MEDIAN_WINDOW);
    if (m->count < MEDIAN_WINDOW) {
        m->count++;
    }
    return median_of(m->buf, m->count);
}
