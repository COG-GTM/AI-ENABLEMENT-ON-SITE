/* Superseded IIR filter kept for reference. Old-style declarations, a disabled block, and a macro that hides a call. */
#include <stdint.h>

#define APPLY(f, x) old_filter_step((f), (x))

typedef struct { int32_t y; int32_t a; } old_filter_t;

int32_t old_filter_step(f, x)
old_filter_t *f;
int32_t x;
{
    f->y = f->y + ((x - f->y) * f->a >> 8);
    return f->y;
}

#if 0
int32_t old_filter_batch(old_filter_t *f, const int32_t *in, int32_t *out, int n)
{
    for (int i = 0; i < n; i++) out[i] = APPLY(f, in[i]);
    return n;
}
#endif
