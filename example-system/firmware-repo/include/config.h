/* Build-time configuration shared by every module. */
#ifndef HUB_CONFIG_H
#define HUB_CONFIG_H

#include <stdint.h>

#define HUB_TICK_HZ        1000u
#define HUB_CHANNELS       4u
#define HUB_TELEMETRY_LEN  24u
#define HUB_MAX_COMMANDS   8u

#if defined(BOARD_REV_C)
#  define HUB_ADC_BITS 12
#elif defined(BOARD_REV_B)
#  define HUB_ADC_BITS 10
#else
#  define HUB_ADC_BITS 12
#endif

typedef int32_t q16_t;   /* Q16.16 fixed point */

#endif
