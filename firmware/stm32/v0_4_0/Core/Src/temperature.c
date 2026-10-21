#include "main.h"
#include "temperature.h"
#include "pilot_config.h"
#include <string.h>
static uint8_t roms[2][8],count,setup[2],bus_status,cycle_status;
static uint8_t state,index_byte,slot,scratch[9],running,pending;
static uint32_t last_tick,cycle;
static uint64_t elapsed_ms,next_cycle,conversion_end,start_us,ready_us;
static TemperatureRecord result;
enum { IDLE, CONVERT_WAIT, SELECT_PROBE, MATCH_BYTES, READ_COMMAND, READ_BYTES };
uint8_t Temperature_CRC8(const uint8_t *bytes,unsigned n) {
    uint8_t crc=0;
    for(unsigned i=0;i<n;++i)for(unsigned b=0;b<8;++b){
        unsigned mix=(crc^(bytes[i]>>b))&1U;crc>>=1;if(mix)crc^=0x8c;
    }return crc;
}
static void match(unsigned i) { OW_WriteByte(0x55);for(unsigned b=0;b<8;++b)OW_WriteByte(roms[i][b]); }
void Temperature_ROM(unsigned i,char text[17]) {
    const char hex[]="0123456789abcdef";
    for(unsigned b=0;b<8;++b){uint8_t x=i<count?roms[i][b]:0;text[2*b]=hex[x>>4];text[2*b+1]=hex[x&15];}text[16]=0;
}
uint8_t Temperature_Count(void) { return count; }
void Temperature_Init(void) { OW_Init(); }
void Temperature_Prepare(void) {
    running=pending=count=bus_status=0;memset(roms,0,sizeof roms);
    setup[0]=setup[1]=TEMP_MISSING;
    /* Standard Search ROM, bounded to 3 devices; an extra/unknown device
     * invalidates topology rather than silently selecting two of them. */
    uint8_t previous[8]={0};unsigned last=0,done=0;
    for(unsigned attempt=0;attempt<3 && !done;++attempt){
        if(!OW_Reset()){if(count)bus_status=TEMP_TOPOLOGY;break;}
        OW_WriteByte(0xf0);uint8_t found[8]={0};unsigned next=0;
        for(unsigned bit=1;bit<=64;++bit){
            unsigned a=OW_ReadBit(),b=OW_ReadBit(),choice;
            if(a&&b){bus_status=TEMP_TOPOLOGY;break;}
            if(a!=b)choice=a;
            else {choice=bit<last?((previous[(bit-1)/8]>>((bit-1)%8))&1U):(bit==last);if(!choice)next=bit;}
            found[(bit-1)/8]|=(uint8_t)(choice<<((bit-1)%8));OW_WriteBit(choice);
        }
        if(bus_status)break;
        if(found[0]!=0x28 || Temperature_CRC8(found,8) || count==2){bus_status=TEMP_TOPOLOGY;break;}
        memcpy(roms[count++],found,8);memcpy(previous,found,8);last=next;done=next==0;
    }
    if(count==2 && memcmp(roms[0],roms[1],8)>0){uint8_t t[8];memcpy(t,roms[0],8);memcpy(roms[0],roms[1],8);memcpy(roms[1],t,8);}
    if(bus_status)return;
    for(unsigned i=0;i<count;++i){
        setup[i]=TEMP_BUS;if(!OW_Reset())continue;match(i);OW_WriteByte(0xb4);
        if(!OW_ReadBit()){setup[i]=TEMP_PARASITE;continue;}
        if(!OW_Reset())continue;
        match(i);OW_WriteByte(0x4e);
        /* Volatile sentinels detect sensor power/reset during a session.
         * No Copy Scratchpad/EEPROM writes. Alarms are unused. */
        OW_WriteByte(0x5a);OW_WriteByte(0xa5);OW_WriteByte(0x7f);setup[i]=TEMP_OK;
    }
}
void Temperature_Begin(uint32_t tick) {
    last_tick=tick;elapsed_ms=0;next_cycle=20;cycle=0;state=IDLE;pending=0;running=1;
}
void Temperature_Stop(void){running=0;state=IDLE;pending=0;}
int Temperature_Pop(TemperatureRecord *r){if(!pending)return 0;*r=result;pending=0;return 1;}
/* HAL tick interval, offset by first TIM3 overflow. Resolution 1 ms,
 * epoch alignment uncertainty ~1 ms; not an ADC-aperture timestamp. */
static uint64_t now_us(void){uint32_t tick=HAL_GetTick();elapsed_ms+=(uint32_t)(tick-last_tick);last_tick=tick;uint64_t ms=elapsed_ms;return ms*1000U>=PILOT_PERIOD_US?ms*1000U-PILOT_PERIOD_US:0;}
static void emit(uint8_t status,int16_t raw){
    result.cycle=cycle;result.slot=slot;result.status=status;result.raw16=raw;
    result.start_us=start_us;result.ready_us=ready_us;result.read_us=now_us();
    Temperature_ROM(slot,result.rom);pending=1;
    if(++slot==2){state=IDLE;++cycle;}else state=SELECT_PROBE;
}
void Temperature_Service(void){
    if(!running)return;
    uint32_t tick=HAL_GetTick();elapsed_ms+=(uint32_t)(tick-last_tick);last_tick=tick;
    if(pending)return;
    switch(state){
    case IDLE:
        if(elapsed_ms<next_cycle)return;
        next_cycle=elapsed_ms+1000;slot=0;cycle_status=0;start_us=ready_us=now_us();
        if(bus_status||!count){state=SELECT_PROBE;return;}
        if(!OW_Reset()){cycle_status=TEMP_BUS;ready_us=now_us();state=SELECT_PROBE;return;}
        OW_WriteByte(0xcc);OW_WriteByte(0x44);
        /* Record command completion, conservative 800 ms wait (750 max). */
        start_us=now_us();conversion_end=elapsed_ms+800;state=CONVERT_WAIT;break;
    case CONVERT_WAIT:
        if(elapsed_ms<conversion_end)return;
        ready_us=now_us();
        if(!OW_ReadBit()){cycle_status=TEMP_TIMEOUT;}
        state=SELECT_PROBE;break;
    case SELECT_PROBE:
        if(bus_status){emit(bus_status,0);return;}
        if(cycle_status){emit(cycle_status,0);return;}
        if(slot>=count){emit(TEMP_MISSING,0);return;}
        if(setup[slot]){emit(setup[slot],0);return;}
        if(!OW_Reset()){emit(TEMP_BUS,0);return;}
        OW_WriteByte(0x55);index_byte=0;state=MATCH_BYTES;break;
    case MATCH_BYTES:
        OW_WriteByte(roms[slot][index_byte++]);if(index_byte==8)state=READ_COMMAND;break;
    case READ_COMMAND:
        OW_WriteByte(0xbe);index_byte=0;state=READ_BYTES;break;
    case READ_BYTES:
        scratch[index_byte++]=OW_ReadByte();if(index_byte<9)break;
        if(Temperature_CRC8(scratch,9)){emit(TEMP_CRC,0);break;}
        if(scratch[2]!=0x5a||scratch[3]!=0xa5||scratch[4]!=0x7f){emit(TEMP_RESET,0);break;}
        {int16_t raw=(int16_t)((uint16_t)scratch[0]|((uint16_t)scratch[1]<<8));
        emit(raw < -880 || raw > 2000?TEMP_RANGE:TEMP_OK,raw);}break;
    default:break;
    }
}
