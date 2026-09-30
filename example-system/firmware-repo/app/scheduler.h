/* Cooperative tick scheduler. Portable: no hardware, callers supply the tick. */
#ifndef HUB_SCHEDULER_H
#define HUB_SCHEDULER_H

#include <stdbool.h>
#include <stdint.h>

#include "config.h"

typedef void (*task_fn)(void *ctx);

typedef struct {
    task_fn fn;
    void *ctx;
    uint32_t period_ticks;
    uint32_t next_due;
    bool enabled;
} task_t;

typedef struct {
    task_t tasks[HUB_MAX_COMMANDS];
    uint8_t count;
    uint32_t tick;
    uint32_t tick_hz;
    uint32_t overruns;
} scheduler_t;

void scheduler_init(scheduler_t *s, uint32_t tick_hz);
bool scheduler_add(scheduler_t *s, task_fn fn, void *ctx, uint32_t period_ms);
void scheduler_tick(scheduler_t *s);
void scheduler_run_pending(scheduler_t *s);

#endif
