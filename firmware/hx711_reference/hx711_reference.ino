/* HX711 raw comparator acquisition, Arduino Uno / ATmega328P.
 * No tare, calibration, averaging or imposed sampling rate. Channel A, gain 128.
 * DOUT D2; PD_SCK D3. USB serial 115200. RATE is a physical module setting.
 * No HX711 library required. Clock pulses cannot be stretched by interrupts.
 */
#include <Arduino.h>
#include <util/atomic.h>
#include <stdlib.h>
#include <string.h>

const uint8_t DOUT_PIN=2, SCK_PIN=3;
const char RELEASE[]="HX711_RAW_R1";
uint32_t token=0, seq=0, dropped=0, lastReady=0, lastError=0;
bool running=false, overflow=false;
char command[40]; uint8_t used=0;

uint16_t crc16(const char *p) {
  uint16_t crc=0xffff;
  while(*p) {crc^=(uint16_t)(uint8_t)*p++<<8;
    for(uint8_t i=0;i<8;i++) crc=crc&0x8000?(crc<<1)^0x1021:crc<<1;
  } return crc;
}
void frame(const char *body) {
  char tail[8]; snprintf(tail,sizeof tail,"*%04X\n",crc16(body));
  Serial.print(body); Serial.print(tail);
}
void metadata() {
  char body[56]; snprintf(body,sizeof body,"M,1,%s,128,%lu",RELEASE,(unsigned long)token); frame(body);
}
void handleCommand() {
  command[used]=0;
  if(!strcmp(command,"HELLO")) metadata();
  else if(!strcmp(command,"STOP")) {
    running=false; char body[64];
    snprintf(body,sizeof body,"S,%lu,%lu,%lu",(unsigned long)token,(unsigned long)seq,(unsigned long)dropped);frame(body);
  } else if(!strncmp(command,"START,",6)) {
    char *end; unsigned long value=strtoul(command+6,&end,10);
    if(command[6]>='1' && command[6]<='9' && !*end && value) {
      running=false;token=value;seq=dropped=0;lastReady=millis();lastError=lastReady;
      metadata();running=true;
    }
  }
}
int32_t readRaw() {
  uint32_t value=0;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    for(uint8_t i=0;i<24;i++) {
      digitalWrite(SCK_PIN,HIGH);delayMicroseconds(2);
      value=(value<<1)|(digitalRead(DOUT_PIN)?1U:0U);
      digitalWrite(SCK_PIN,LOW);delayMicroseconds(2);
    }
    // Pulse 25 selects channel A / gain 128 for the next conversion.
    digitalWrite(SCK_PIN,HIGH);delayMicroseconds(2);
    digitalWrite(SCK_PIN,LOW);delayMicroseconds(2);
  }
  if(value&0x800000UL)value|=0xff000000UL;
  return (int32_t)value;
}
void setup() {
  pinMode(SCK_PIN,OUTPUT);digitalWrite(SCK_PIN,LOW);
  pinMode(DOUT_PIN,INPUT_PULLUP);Serial.begin(115200);
  // Explicit startup reset only; START/STOP never resets the bridge.
  digitalWrite(SCK_PIN,HIGH);delayMicroseconds(80);digitalWrite(SCK_PIN,LOW);
  lastReady=millis();metadata();
}
void loop() {
  for(uint8_t n=0;n<40 && Serial.available();n++) {
    char c=Serial.read();
    if(c=='\n') {if(!overflow)handleCommand();used=0;overflow=false;}
    else if(c!='\r') {if(used<sizeof(command)-1 && !overflow)command[used++]=c;else overflow=true;}
  }
  if(digitalRead(DOUT_PIN)==LOW) {
    uint32_t stamp=micros();int32_t raw=readRaw();lastReady=millis();
    if(running) {
      char body[64];int size=snprintf(body,sizeof body,"D,%lu,%lu,%lu,%ld,%lu",
        (unsigned long)token,(unsigned long)seq,(unsigned long)stamp,(long)raw,(unsigned long)dropped);
      if(size>0 && size+6<=Serial.availableForWrite())frame(body);else dropped++;
      seq++;
    }
  } else if(running && millis()-lastReady>1500UL && millis()-lastError>1000UL) {
    char body[48];snprintf(body,sizeof body,"E,%lu,NOT_READY",(unsigned long)token);frame(body);lastError=millis();
  }
}
