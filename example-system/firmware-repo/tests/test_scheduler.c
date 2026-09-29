/* Host test for the scheduler (already exists in the tree: reuse it, do not add a second framework). */
#include <stdio.h>

#include "scheduler.h"

static int fired;
static void tick_task(void *ctx) { (void)ctx; fired++; }

int main(void)
{
    scheduler_t s;
    scheduler_init(&s, 1000);
    if (!scheduler_add(&s, tick_task, 0, 10)) {
        return 1;
    }
    for (int i = 0; i < 100; i++) {
        scheduler_tick(&s);
        scheduler_run_pending(&s);
    }
    printf("fired=%d overruns=%lu\n", fired, (unsigned long)s.overruns);
    return fired == 10 && s.overruns == 0 ? 0 : 1;
}
