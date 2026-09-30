/* Cooperative tick scheduler (REQ-SCHED-001..004). Pure C: builds on any host, tested in tests/test_scheduler.c. */
#include "scheduler.h"

#include <string.h>

void scheduler_init(scheduler_t *s, uint32_t tick_hz)
{
    memset(s, 0, sizeof(*s));
    s->tick_hz = tick_hz ? tick_hz : HUB_TICK_HZ;
}

bool scheduler_add(scheduler_t *s, task_fn fn, void *ctx, uint32_t period_ms)
{
    if (s->count >= HUB_MAX_COMMANDS || fn == 0 || period_ms == 0) {
        return false;
    }
    task_t *t = &s->tasks[s->count++];
    t->fn = fn;
    t->ctx = ctx;
    t->period_ticks = (period_ms * s->tick_hz) / 1000u;
    if (t->period_ticks == 0) {
        t->period_ticks = 1;
    }
    t->next_due = s->tick + t->period_ticks;
    t->enabled = true;
    return true;
}

void scheduler_tick(scheduler_t *s)
{
    s->tick++;
}

void scheduler_run_pending(scheduler_t *s)
{
    for (uint8_t i = 0; i < s->count; i++) {
        task_t *t = &s->tasks[i];
        if (!t->enabled) {
            continue;
        }
        if ((int32_t)(s->tick - t->next_due) >= 0) {
            if ((int32_t)(s->tick - t->next_due) >= (int32_t)t->period_ticks) {
                s->overruns++;
            }
            t->next_due += t->period_ticks;
            t->fn(t->ctx);   /* dispatch through a function pointer: the scanner cannot see the callee */
        }
    }
}
