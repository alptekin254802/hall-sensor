#ifndef PILOT_CONFIG_H
#define PILOT_CONFIG_H
/* Diagnostic starting point, not a final measurement setting. */
#define PILOT_DIAGNOSTIC 1
#define PILOT_VERSION "0.4.0"
#ifndef PILOT_CHANNEL_COUNT
#define PILOT_CHANNEL_COUNT 4U
#endif
#if PILOT_CHANNEL_COUNT != 2U && PILOT_CHANNEL_COUNT != 4U
#error "Only two or four physically connected channels are supported"
#endif
#ifndef PILOT_BUILD_ID
#define PILOT_BUILD_ID "UNIDENTIFIED"
#endif
#ifndef PILOT_RATE_HZ
#define PILOT_RATE_HZ (PILOT_CHANNEL_COUNT == 4U ? 100U : 200U)
#endif
#ifndef PILOT_BAUD
#define PILOT_BAUD 230400U
#endif
#define PILOT_NEXTION_BAUD 9600U
#define PILOT_NEXTION_PERIOD_MS 500U
#define PILOT_PERIOD_US (1000000U / PILOT_RATE_HZ)
#define PILOT_QUEUE_LEN 128U
#define PILOT_RECORD_MAX_BYTES (96U + 5U * (PILOT_CHANNEL_COUNT - 2U))
#define PILOT_IRQ_LIMIT_US 500U
#if (PILOT_RATE_HZ < 20U) || (PILOT_RATE_HZ > 1000U) || (1000000U % PILOT_RATE_HZ)
#error "Use an integer period, 20..1000 pairs/s; check the UART budget."
#endif
#if ((PILOT_RECORD_MAX_BYTES * PILOT_RATE_HZ + 300U) * 10U * 100U > PILOT_BAUD * 85U)
#error "Worst-case diagnostic records exceed 85 percent of UART capacity."
#endif
#endif
