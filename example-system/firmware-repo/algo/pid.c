/* Fixed-point PID controller. Pure integer math, no hardware. */
#include "pid.h"

#include "fixed_point.h"

void pid_init(pid_t *p, q16_t kp, q16_t ki, q16_t kd, q16_t out_min, q16_t out_max)
{
    p->kp = kp;
    p->ki = ki;
    p->kd = kd;
    p->integral = 0;
    p->prev_error = 0;
    p->out_min = out_min;
    p->out_max = out_max;
}

q16_t pid_step(pid_t *p, q16_t setpoint, q16_t measured)
{
    q16_t error = setpoint - measured;
    p->integral = q16_clamp(p->integral + error, p->out_min, p->out_max);   /* anti-windup */
    q16_t deriv = error - p->prev_error;
    p->prev_error = error;
    q16_t out = q16_mul(p->kp, error) + q16_mul(p->ki, p->integral) + q16_mul(p->kd, deriv);
    return q16_clamp(out, p->out_min, p->out_max);
}
