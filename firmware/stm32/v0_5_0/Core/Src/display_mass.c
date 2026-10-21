/* Foreground-only display calculations. Never modifies the acquisition queue. */
#include "display_mass.h"
#include "display_knots.h"
#include <stdio.h>
#include <string.h>
static uint32_t count, sum, first, last, have_previous, invalid;
static uint32_t zero_sum, zero_epoch, zero_pending, ready, have_result;
static DisplayRecord result;

double DisplayMass_Convert(double response, uint32_t *status) {
    *status=DISPLAY_OK;
    /* Signed zero indication only; this extension is not calibration evidence. */
    if (response < -x_knots[1]) { *status=DISPLAY_LOW; return 0; }
    if (response < 0) { *status=DISPLAY_NEGATIVE_ZERO; return response*mass_knots[1]/x_knots[1]; }
    if (response > x_knots[12]) { *status=DISPLAY_HIGH; return 0; }
    for (unsigned i=1;i<13;++i) if (response<=x_knots[i])
        return mass_knots[i-1]+(response-x_knots[i-1])*(mass_knots[i]-mass_knots[i-1])/(x_knots[i]-x_knots[i-1]);
    return 0;
}
void DisplayMass_Start(void) {
    count=sum=first=last=have_previous=invalid=ready=have_result=zero_pending=0;
    /* An unloaded zero survives PC STOP/START, but not MCU power/reset. */
}
void DisplayMass_Init(void) {
    zero_sum=zero_epoch=0; memset(&result,0,sizeof result); DisplayMass_Start();
}
void DisplayMass_Zero(void) {
    count=sum=have_previous=invalid=ready=have_result=0; zero_pending=1;
}
void DisplayMass_Add(uint32_t seq, const uint16_t samples[4], uint32_t flags) {
    if (have_previous && seq!=last+1U) {count=sum=0;invalid=DISPLAY_GAP;}
    if (!count) first=seq;
    last=seq;have_previous=1;
    for (unsigned i=0;i<4;++i) {
        sum+=samples[i];
        if (samples[i]==0 || samples[i]>=4095) invalid=DISPLAY_RAIL;
    }
    if (flags) invalid=DISPLAY_GAP;
    if (++count<DISPLAY_WINDOW) return;
    if (zero_pending && !invalid) {zero_sum=sum;++zero_epoch;zero_pending=0;}
    result=(DisplayRecord){seq,first,count,sum,zero_sum,zero_epoch,DISPLAY_WAIT_ZERO,0};
    if (invalid) result.status=invalid;
    else if (zero_epoch) {
        double g=DisplayMass_Convert(((double)zero_sum-sum)/(4.0*DISPLAY_WINDOW),&result.status);
        result.mass_mg=(int32_t)(g*1000.0+(g<0?-0.5:0.5));
    }
    count=sum=invalid=0;ready=have_result=1;
}
int DisplayMass_Pop(DisplayRecord *out) {
    if(!ready)return 0;
    *out=result;ready=0;return 1;
}
void DisplayMass_Text(char *out, unsigned capacity) {
    if (zero_pending) {snprintf(out,capacity,"ZEROING");return;}
    if (!have_result) {snprintf(out,capacity,"%s",zero_epoch?"WARMUP":"ZERO?");return;}
    const char *label=0;
    switch(result.status) {
    case DISPLAY_WAIT_ZERO:label="ZERO?";break;
    case DISPLAY_LOW:label="LOW";break;
    case DISPLAY_HIGH:label="HIGH";break;
    case DISPLAY_RAIL:label="ADC RAIL";break;
    case DISPLAY_GAP:label="DATA GAP";break;
    default:break;
    }
    if(label){snprintf(out,capacity,"%s",label);return;}
    int32_t mg=result.mass_mg;
    long grams=(long)((mg+(mg<0?-500:500))/1000);
    snprintf(out,capacity,"%ld g",grams);
}
