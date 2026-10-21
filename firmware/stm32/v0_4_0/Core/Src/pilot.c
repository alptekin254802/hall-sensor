/* EXT002 diagnostic acquisition. No averaging, tare subtraction, force model,
 * EMA, absolute value or clipping. See pilot/README.md and RM0008 ADC/DMA/TIM3.
 * Firmware is a bench-test candidate; compilation is not device validation. */
#include "pilot.h"
#include "nextion_pilot.h"
#include "temperature.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>

/* Record flags: bit0 queue loss, bit1 UART TX error, bit2 UART RX error.
 * Fatal acquisition bits: 0 DMA, 1 timing/phase, 2 ADC/start, 3 watchdog,
 * 4 sequence exhaustion. Fatal acquisition does NOT emit invented ADC values. */
typedef struct {
    uint64_t t_us;
    uint32_t seq, flags, dropped, tx_errors, dma_phase_us;
    uint16_t s1, s2;
#if PILOT_CHANNEL_COUNT == 4U
    uint16_t s3, s4;
#endif
} Record;
_Static_assert(sizeof(Record) == (PILOT_CHANNEL_COUNT == 4U ? 40U : 32U), "Update the memory budget");
static Record queue[PILOT_QUEUE_LEN];
static volatile uint32_t head, tail, seq, dropped, tx_errors, rx_errors;
static volatile uint32_t sticky, fatal, active, last_tick;
static uint32_t last_cycles, have_previous;
static uint16_t adc_pairs[2U * PILOT_CHANNEL_COUNT] __attribute__((aligned(4)));
static ADC_HandleTypeDef *a;
static UART_HandleTypeDef *u;
static DMA_HandleTypeDef dma;
static uint8_t rx_byte;
static char command[64];
static volatile uint32_t command_len, command_ready, command_overflow;
static char session[33];
static char line[1536];

static void atomic_or(volatile uint32_t *p, uint32_t bits) {
    uint32_t old;
    do { old=__LDREXW(p); } while (__STREXW(old|bits,p));
    __DMB();
}
static void u64_decimal(uint64_t value, char out[21]) {
    char reverse[20]; unsigned n=0;
    do { reverse[n++]=(char)('0'+value%10U); value/=10U; } while (value);
    for (unsigned i=0;i<n;++i) out[i]=reverse[n-1U-i];
    out[n]=0;
}
static uint16_t crc16(const char *s, size_t n) {
    uint16_t c = 0xffff;
    for (size_t i=0; i<n; ++i) {
        c ^= (uint16_t)(uint8_t)s[i] << 8;
        for (unsigned j=0; j<8; ++j)
            c = (uint16_t)((c & 0x8000) ? (c << 1) ^ 0x1021 : c << 1);
    }
    return c;
}
/* Only foreground transmits; ADC DMA interrupts remain enabled. */
static int send_body(const char *body) {
    size_t n = strlen(body);
    char suffix[8];
    int k=snprintf(suffix,sizeof suffix,"*%04X\n",crc16(body,n));
    if (HAL_UART_Transmit(u,(uint8_t *)body,(uint16_t)n,100)!=HAL_OK ||
        HAL_UART_Transmit(u,(uint8_t *)suffix,(uint16_t)k,100)!=HAL_OK) {
        ++tx_errors; atomic_or(&sticky,2U);
        /* Terminate any partial frame so the next record can resynchronize. */
        uint8_t lf='\n'; (void)HAL_UART_Transmit(u,&lf,1,10);
        return 0;
    }
    return 1;
}
static void fail(uint32_t bits) {
    atomic_or(&fatal,bits);
    TIM3->CR1 &= ~TIM_CR1_CEN;
    DMA1_Channel1->CCR &= ~DMA_CCR_EN;
}
static void capture(unsigned offset) {
    if (!active || fatal) return;
    uint32_t phase=TIM3->CNT, now=DWT->CYCCNT, tick=HAL_GetTick();
    uint32_t expected_cycles=72U * PILOT_PERIOD_US;
    uint32_t elapsed=now-last_cycles;
    if (phase < 21U * PILOT_CHANNEL_COUNT - 2U || phase > PILOT_IRQ_LIMIT_US ||
        (have_previous && (elapsed < expected_cycles-72U*PILOT_IRQ_LIMIT_US ||
                           elapsed > expected_cycles+72U*PILOT_IRQ_LIMIT_US ||
                           tick-last_tick > PILOT_PERIOD_US/1000U+2U)) ||
        offset != ((seq & 1U) ? PILOT_CHANNEL_COUNT : 0U)) {
        fail(2U); return;
    }
    last_cycles=now; last_tick=tick; have_previous=1;
    if (seq==UINT32_MAX) { fail(16U); return; }
    uint32_t current=seq++;
    uint32_t next=(head+1U)%PILOT_QUEUE_LEN;
    if (next==tail) { ++dropped; atomic_or(&sticky,1U); return; }
    Record *r=&queue[head];
    r->t_us=(uint64_t)current*PILOT_PERIOD_US;
    r->seq=current; r->s1=adc_pairs[offset]; r->s2=adc_pairs[offset+1U];
#if PILOT_CHANNEL_COUNT == 4U
    r->s3=adc_pairs[offset+2U]; r->s4=adc_pairs[offset+3U];
#endif
    r->flags=sticky; r->dropped=dropped; r->tx_errors=tx_errors;
    r->dma_phase_us=phase;
    __DMB(); head=next;
}
void DMA1_Channel1_IRQHandler(void) {
    uint32_t flags=DMA1->ISR;
    /* Both halves pending means software may have missed/overwritten a pair. */
    if ((flags&DMA_ISR_TEIF1) ||
        ((flags&(DMA_ISR_HTIF1|DMA_ISR_TCIF1))==(DMA_ISR_HTIF1|DMA_ISR_TCIF1))) {
        DMA1->IFCR=DMA_IFCR_CGIF1; fail(1U); return;
    }
    HAL_DMA_IRQHandler(&dma);
}
void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *adc) {
    if (adc==a) capture(0);
}
void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *adc) {
    if (adc==a) capture(PILOT_CHANNEL_COUNT);
}
void HAL_ADC_ErrorCallback(ADC_HandleTypeDef *adc) {
    if (adc==a) fail(4U);
}
void USART1_IRQHandler(void) { HAL_UART_IRQHandler(u); }
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart) {
    NextionPilot_RxComplete(uart);
    if (uart!=u) return;
    if (!command_ready) {
        if (rx_byte=='\n') {
            command[command_len]=0; __DMB(); command_ready=1;
        } else if (rx_byte!='\r') {
            if (command_len < sizeof command-1) command[command_len++]=(char)rx_byte;
            else command_overflow=1;
        }
    } else { ++rx_errors; atomic_or(&sticky,4U); }
    if (HAL_UART_Receive_IT(u,&rx_byte,1)!=HAL_OK) { ++rx_errors; atomic_or(&sticky,4U); }
}
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart) {
    NextionPilot_Error(uart);
    if (uart==u) {
        ++rx_errors; atomic_or(&sticky,4U);
        command_overflow=1;
        (void)HAL_UART_Receive_IT(u,&rx_byte,1);
    }
}
static int pop_send(void) {
    if (tail==head) return 0;
    __DMB(); Record r=queue[tail];
    tail=(tail+1U)%PILOT_QUEUE_LEN;
    const uint16_t samples[PILOT_CHANNEL_COUNT] = {r.s1, r.s2,
#if PILOT_CHANNEL_COUNT == 4U
        r.s3, r.s4,
#endif
    };
    NextionPilot_Sample(samples);
    char time_text[21]; u64_decimal(r.t_us,time_text);
    int n=snprintf(line,sizeof line,
#if PILOT_CHANNEL_COUNT == 4U
        "D,%lu,%s,%u,%u,%u,%u,%lu,%lu,%lu,%lu",
        (unsigned long)r.seq,time_text,r.s1,r.s2,r.s3,r.s4,
#else
        "D,%lu,%s,%u,%u,%lu,%lu,%lu,%lu",
        (unsigned long)r.seq,time_text,r.s1,r.s2,
#endif
        (unsigned long)r.flags,(unsigned long)r.dropped,
        (unsigned long)r.tx_errors,(unsigned long)r.dma_phase_us);
    if (n<0 || (unsigned)n+6U>PILOT_RECORD_MAX_BYTES) { fail(4U); return 0; }
    (void)send_body(line); return 1;
}
static void metadata(void) {
    snprintf(line,sizeof line,
        "M,{\"protocol\":%u,\"channel_count\":%u,\"session_id\":\"%s\",\"firmware\":\"%s\","
        "\"build_id\":\"%s\",\"rate_hz\":%lu,\"period_us\":%lu,"
        "\"baud\":%lu,\"core_hz\":72000000,\"adc_hz\":12000000,"
        "\"sample_cycles\":239.5,\"s1\":\"ADC1_IN0_PA0_rank1\","
        "\"s2\":\"ADC1_IN1_PA1_rank2\","
#if PILOT_CHANNEL_COUNT == 4U
        "\"s3\":\"ADC1_IN5_PA5_rank3\",\"s4\":\"ADC1_IN6_PA6_rank4\","
#endif
        "\"scan_conversion_us\":%u,"
        "\"rank_spacing_us\":21,\"time_basis\":\"nominal_TIM3_trigger_seq0_epoch\","
        "\"display_refresh\":true,\"display_baud\":%u,\"display_period_ms\":%u,\"display_tare\":\"display_only\",\"display_link_verified\":false,\"analog_rc_nominal\":null,\"analog_rc_note\":\"legacy S1/S2 schematic 1k/100nF; actual paths unverified\","
        "\"temperature_stream\":1,\"hardware_id\":null,\"head_id\":null}",
        PILOT_CHANNEL_COUNT == 4U ? 2U : 1U, PILOT_CHANNEL_COUNT, session,PILOT_VERSION,
        PILOT_BUILD_ID,(unsigned long)PILOT_RATE_HZ,
        (unsigned long)PILOT_PERIOD_US,(unsigned long)PILOT_BAUD,21U * PILOT_CHANNEL_COUNT,
        PILOT_NEXTION_BAUD, PILOT_NEXTION_PERIOD_MS);
    (void)send_body(line);
}
static void temperature_metadata(void) {
    char r0[17],r1[17];Temperature_ROM(0,r0);Temperature_ROM(1,r1);
    snprintf(line,sizeof line,"Q,{\"protocol\":1,\"pin\":\"PB7\",\"supply_v\":3.3,"
        "\"period_ms\":1000,\"resolution_bits\":12,\"count\":%u,\"roms\":[\"%s\",\"%s\"],"
        "\"time_basis\":\"HAL_tick_relative_first_TIM3_trigger\",\"timestamp_resolution_us\":1000,"
        "\"epoch_uncertainty_us_nominal\":1000,\"physical_tested\":false}",Temperature_Count(),r0,r1);
    (void)send_body(line);
}
/* Keep a distinct telemetry boundary for binary-level protocol verification. */
__attribute__((noinline)) static void temperature_send(void) {
    TemperatureRecord r;if(!Temperature_Pop(&r))return;
    NextionPilot_Temperature(r.slot,r.raw16,r.status);
    char t0[21],t1[21],t2[21],raw[12];u64_decimal(r.start_us,t0);u64_decimal(r.ready_us,t1);u64_decimal(r.read_us,t2);
    if(r.status==TEMP_OK)snprintf(raw,sizeof raw,"%d",r.raw16);else strcpy(raw,"NA");
    snprintf(line,sizeof line,"T,%lu,%u,%s,%s,%s,%s,%s,%u",(unsigned long)r.cycle,r.slot,r.rom,t0,t1,t2,raw,r.status);
    (void)send_body(line);
}
static int init_acquisition(void) {
    if (HAL_RCC_GetHCLKFreq()!=72000000U || HAL_RCC_GetPCLK2Freq()!=72000000U ||
        HAL_RCC_GetPCLK1Freq()!=36000000U ||
        HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC)!=12000000U) return 0;
    __HAL_RCC_DMA1_CLK_ENABLE(); __HAL_RCC_TIM3_CLK_ENABLE();
    TIM3->CR1=0; TIM3->CR2=0; TIM3->PSC=71; TIM3->ARR=PILOT_PERIOD_US-1U;
    TIM3->EGR=TIM_EGR_UG; TIM3->SR=0; TIM3->CR2=TIM_CR2_MMS_1;
    a->Instance=ADC1; a->Init.ScanConvMode=ADC_SCAN_ENABLE;
    a->Init.ContinuousConvMode=DISABLE; a->Init.DiscontinuousConvMode=DISABLE;
    a->Init.ExternalTrigConv=ADC_EXTERNALTRIGCONV_T3_TRGO;
    a->Init.DataAlign=ADC_DATAALIGN_RIGHT; a->Init.NbrOfConversion=PILOT_CHANNEL_COUNT;
    if (HAL_ADC_Init(a)!=HAL_OK) return 0;
    ADC_ChannelConfTypeDef c={0};
    c.Channel=ADC_CHANNEL_0; c.Rank=ADC_REGULAR_RANK_1;
    c.SamplingTime=ADC_SAMPLETIME_239CYCLES_5;
    if (HAL_ADC_ConfigChannel(a,&c)!=HAL_OK) return 0;
    c.Channel=ADC_CHANNEL_1; c.Rank=ADC_REGULAR_RANK_2;
    if (HAL_ADC_ConfigChannel(a,&c)!=HAL_OK) return 0;
    #if PILOT_CHANNEL_COUNT == 4U
    /* PA2/PA3 remain USART2; PA4 remains the legacy LED. Physical routing of
     * PA5/PA6 on the intended spare board must be checked before connection. */
    GPIO_InitTypeDef pins={0};
    pins.Pin=GPIO_PIN_5|GPIO_PIN_6; pins.Mode=GPIO_MODE_ANALOG;
    HAL_GPIO_Init(GPIOA,&pins);
    c.Channel=ADC_CHANNEL_5; c.Rank=ADC_REGULAR_RANK_3;
    if (HAL_ADC_ConfigChannel(a,&c)!=HAL_OK) return 0;
    c.Channel=ADC_CHANNEL_6; c.Rank=ADC_REGULAR_RANK_4;
    if (HAL_ADC_ConfigChannel(a,&c)!=HAL_OK) return 0;
#endif
    /* Internal ADC calibration only. No force tare/reference subtraction. */
    if (HAL_ADCEx_Calibration_Start(a)!=HAL_OK) return 0;
    dma.Instance=DMA1_Channel1; dma.Init.Direction=DMA_PERIPH_TO_MEMORY;
    dma.Init.PeriphInc=DMA_PINC_DISABLE; dma.Init.MemInc=DMA_MINC_ENABLE;
    dma.Init.PeriphDataAlignment=DMA_PDATAALIGN_HALFWORD;
    dma.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;
    dma.Init.Mode=DMA_CIRCULAR; dma.Init.Priority=DMA_PRIORITY_HIGH;
    if (HAL_DMA_Init(&dma)!=HAL_OK) return 0;
    __HAL_LINKDMA(a,DMA_Handle,dma);
    HAL_NVIC_SetPriority(DMA1_Channel1_IRQn,0,0);
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT=0; DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    return 1;
}
static void stop(void) {
    Temperature_Stop();
    /* Stop future triggers, allow a pair already started to finish, then stop timer.
     * Keep CNT running during this grace interval so DMA phase remains meaningful. */
    TIM3->CR2=0;
    if (!fatal) HAL_Delay(1);
    TIM3->CR1 &= ~TIM_CR1_CEN;
    HAL_NVIC_DisableIRQ(DMA1_Channel1_IRQn);
    active=0;
    if (HAL_ADC_Stop_DMA(a)!=HAL_OK) fatal |= 4U;
    NextionPilot_Stop(fatal);
    DMA1->IFCR=DMA_IFCR_CGIF1;
    while (pop_send()) {}
    if (fatal) {
        snprintf(line,sizeof line,"F,%lu,%lu",(unsigned long)seq,(unsigned long)fatal);
        (void)send_body(line);
    }
    snprintf(line,sizeof line,"E,%lu,%lu,%lu,%lu,%lu",(unsigned long)seq,
        (unsigned long)dropped,(unsigned long)tx_errors,(unsigned long)rx_errors,
        (unsigned long)fatal);
    (void)send_body(line);
}
static void start(const char *id) {
    if (strlen(id)!=32) { (void)send_body("X,invalid_session_id"); return; }
    for (unsigned i=0;i<32;++i)
        if (!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f'))) {
            (void)send_body("X,invalid_session_id"); return;
        }
    if (active) {
        if (!strcmp(session,id)) { metadata(); temperature_metadata(); }
        else (void)send_body("X,already_active");
        return;
    }
    if (!strcmp(PILOT_BUILD_ID,"UNIDENTIFIED")) {
        (void)send_body("X,use_build_firmware_script"); return;
    }
    strcpy(session,id);
    head=tail=seq=dropped=tx_errors=rx_errors=sticky=fatal=have_previous=0;
    TIM3->CNT=0; TIM3->SR=0; DMA1->IFCR=DMA_IFCR_CGIF1;
    Temperature_Prepare();
    metadata();
    temperature_metadata();
    if (tx_errors) { (void)send_body("X,metadata_tx_failed"); return; }
    if (HAL_ADC_Start_DMA(a,(uint32_t *)adc_pairs,2U * PILOT_CHANNEL_COUNT)!=HAL_OK ||
        dma.State!=HAL_DMA_STATE_BUSY) { fatal=4U; stop(); return; }
    last_tick=HAL_GetTick();
    HAL_NVIC_ClearPendingIRQ(DMA1_Channel1_IRQn);
    TIM3->CR2=TIM_CR2_MMS_1;
    NextionPilot_Start();
    active=1; HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
    Temperature_Begin(HAL_GetTick());
    TIM3->CR1 |= TIM_CR1_CEN;
}
_Noreturn void Pilot_Run(ADC_HandleTypeDef *adc, UART_HandleTypeDef *uart, UART_HandleTypeDef *display) {
    a=adc; u=uart;
    NextionPilot_Init(display);
    if (!init_acquisition()) {
        (void)send_body("X,acquisition_init_failed");
        NextionPilot_Stop(4U);
        for (;;) { NextionPilot_Service(); __WFI(); }
    }
    Temperature_Init();
    HAL_NVIC_SetPriority(USART1_IRQn,2,0); HAL_NVIC_EnableIRQ(USART1_IRQn);
    (void)HAL_UART_Receive_IT(u,&rx_byte,1);
    (void)send_body("B,EXT002_DIAGNOSTIC_1");
    for (;;) {
        if (command_ready) {
            char local[64]; strcpy(local,command);
            uint32_t bad=command_overflow;
            command_len=command_overflow=0; __DMB(); command_ready=0;
            if (bad) (void)send_body("X,command_corrupt");
            else if (!strncmp(local,"START ",6)) start(local+6);
            else if (!strcmp(local,"STOP")) { if (active) stop(); }
            else (void)send_body("X,unknown_command");
        }
        if (active && !fatal && HAL_GetTick()-last_tick > 3U*PILOT_PERIOD_US/1000U+2U)
            fail(8U);
        if (active && fatal) stop();
        int sent = pop_send();
        NextionPilot_Service();
        if(active && !fatal) { Temperature_Service(); temperature_send(); }
        if (!sent) __WFI();
    }
}
