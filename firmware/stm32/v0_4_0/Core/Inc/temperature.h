#ifndef TEMPERATURE_H
#define TEMPERATURE_H
#include <stdint.h>
enum { TEMP_OK=0, TEMP_MISSING=1, TEMP_BUS=2, TEMP_CRC=3,
       TEMP_RESET=4, TEMP_RANGE=5, TEMP_TIMEOUT=6, TEMP_PARASITE=7,
       TEMP_TOPOLOGY=8 };
typedef struct {
    uint32_t cycle;
    uint8_t slot, status;
    char rom[17];
    uint64_t start_us, ready_us, read_us;
    int16_t raw16;
} TemperatureRecord;
void Temperature_Init(void);
/* Discovery/configuration only before ADC START; identities fixed per session. */
void Temperature_Prepare(void);
void Temperature_Begin(uint32_t tick);
void Temperature_Stop(void);
void Temperature_Service(void);
int Temperature_Pop(TemperatureRecord *record);
uint8_t Temperature_Count(void);
void Temperature_ROM(unsigned slot, char text[17]);
/* Port boundary: PB7 open-drain + external 4.7k to 3V3, external VDD. */
void OW_Init(void);
int OW_Reset(void);
unsigned OW_ReadBit(void);
void OW_WriteBit(unsigned bit);
uint8_t OW_ReadByte(void);
void OW_WriteByte(uint8_t byte);
uint8_t Temperature_CRC8(const uint8_t *bytes, unsigned count);
#endif
