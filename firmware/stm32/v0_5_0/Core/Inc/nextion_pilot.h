#ifndef NEXTION_PILOT_H
#define NEXTION_PILOT_H
#include "main.h"
#include "pilot_config.h"
/* Optional display sink; never owns ADC, raw records or PC UART. */
void NextionPilot_Init(UART_HandleTypeDef *uart);
void NextionPilot_Start(void);
void NextionPilot_Stop(uint32_t fatal_bits);
void NextionPilot_Sample(uint32_t seq, const uint16_t *samples, uint32_t flags);
void NextionPilot_Temperature(unsigned slot, int16_t raw16, unsigned status);
void NextionPilot_Service(void);
void NextionPilot_RxComplete(UART_HandleTypeDef *uart);
void NextionPilot_Error(UART_HandleTypeDef *uart);
#endif
