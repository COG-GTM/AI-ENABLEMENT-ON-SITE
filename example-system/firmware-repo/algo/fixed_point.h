/* Q16.16 helpers, header-only. Portable. */
#ifndef HUB_FIXED_POINT_H
#define HUB_FIXED_POINT_H

#include <stdint.h>

#include "config.h"

#define Q16_ONE   ((q16_t)0x00010000)
#define Q16(x)    ((q16_t)((x) * 65536.0))

static inline q16_t q16_mul(q16_t a, q16_t b)
{
    return (q16_t)(((int64_t)a * (int64_t)b) >> 16);
}

static inline q16_t q16_clamp(q16_t v, q16_t lo, q16_t hi)
{
    if (v < lo) {
        return lo;
    }
    if (v > hi) {
        return hi;
    }
    return v;
}

#endif
