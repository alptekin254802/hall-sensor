#ifndef DISPLAY_MASS_H
#define DISPLAY_MASS_H
#include <stdint.h>
#define DISPLAY_WINDOW 100U
enum { DISPLAY_WAIT_ZERO, DISPLAY_OK, DISPLAY_NEGATIVE_ZERO, DISPLAY_LOW,
       DISPLAY_HIGH, DISPLAY_RAIL, DISPLAY_GAP };
typedef struct {
    uint32_t last_seq, first_seq, count, sum, zero_sum, zero_epoch, status;
    int32_t mass_mg;
} DisplayRecord;
void DisplayMass_Init(void);
void DisplayMass_Start(void);
void DisplayMass_Zero(void);
void DisplayMass_Add(uint32_t seq, const uint16_t samples[4], uint32_t flags);
int DisplayMass_Pop(DisplayRecord *out);
void DisplayMass_Text(char *out, unsigned capacity);
double DisplayMass_Convert(double response, uint32_t *status);
#endif
