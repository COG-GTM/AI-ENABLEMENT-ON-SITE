/* Fixed-point PID controller (REQ-CTRL-001..003). Portable; golden vectors in tests/vectors/pid_vectors.csv. */
#ifndef HUB_PID_H
#define HUB_PID_H

#include "config.h"

typedef struct {
    q16_t kp, ki, kd;
    q16_t integral;
    q16_t prev_error;
    q16_t out_min, out_max;
} pid_t;

void  pid_init(pid_t *p, q16_t kp, q16_t ki, q16_t kd, q16_t out_min, q16_t out_max);
q16_t pid_step(pid_t *p, q16_t setpoint, q16_t measured);

#endif
