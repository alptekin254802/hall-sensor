#ifndef PILOT_H
#define PILOT_H
#include "main.h"
#include "pilot_config.h"
_Noreturn void Pilot_Run(ADC_HandleTypeDef *adc, UART_HandleTypeDef *uart, UART_HandleTypeDef *display);
#endif
