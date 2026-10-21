#include "main.h"
#include "temperature.h"
/* Only timing-critical 1/read slots mask interrupts (at most ~13 us).
 * Reset and write-zero waits leave IRQs enabled. ADC TIM3/DMA stay running.
 * 72 MHz/DWT availability is checked by acquisition initialization. */
static void wait_us(uint32_t us) {
    uint32_t begin=DWT->CYCCNT;
    while ((uint32_t)(DWT->CYCCNT-begin)<us*72U) {}
}
static void low(void) { GPIOB->BRR=GPIO_PIN_7; }
static void release(void) { GPIOB->BSRR=GPIO_PIN_7; }
static unsigned pin(void) { return (GPIOB->IDR & GPIO_PIN_7)!=0; }
void OW_Init(void) {
    __HAL_RCC_GPIOB_CLK_ENABLE(); release();
    GPIO_InitTypeDef cfg={0};cfg.Pin=GPIO_PIN_7;cfg.Mode=GPIO_MODE_OUTPUT_OD;
    cfg.Speed=GPIO_SPEED_FREQ_HIGH;HAL_GPIO_Init(GPIOB,&cfg);
}
int OW_Reset(void) {
    release();wait_us(5);if (!pin()) return 0;
    low();wait_us(500);release();wait_us(70);
    unsigned presence=!pin();wait_us(430);
    return presence && pin();
}
void OW_WriteBit(unsigned bit) {
    if (bit) {
        uint32_t mask=__get_PRIMASK();__disable_irq();
        low();wait_us(6);release();__set_PRIMASK(mask);wait_us(64);
    } else { low();wait_us(60);release();wait_us(10); }
}
unsigned OW_ReadBit(void) {
    uint32_t mask=__get_PRIMASK();__disable_irq();
    low();wait_us(3);release();wait_us(10);unsigned value=pin();
    __set_PRIMASK(mask);wait_us(57);return value;
}
void OW_WriteByte(uint8_t byte) {
    for (unsigned i=0;i<8;++i) { OW_WriteBit(byte&1U);byte>>=1; }
}
uint8_t OW_ReadByte(void) {
    uint8_t byte=0;for(unsigned i=0;i<8;++i)byte|=(uint8_t)(OW_ReadBit()<<i);
    return byte;
}
