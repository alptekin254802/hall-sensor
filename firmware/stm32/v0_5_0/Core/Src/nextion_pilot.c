/* Existing HMI contract: USART2 9600 8N1, t0 text, waveform ID 2/channel 0,
 * raw ASCII 'T' for UNLOADED zero. Frozen A mass display; no HMI upload.
 * ADC DMA priority 0, PC UART priority 2, display UART priority 3.
 * All formatting is foreground; the display never waits for a reply. */
#include "nextion_pilot.h"
#include "display_mass.h"
#include <stdio.h>
#include <string.h>

#define RX_SIZE 64U
#define TX_SIZE 96U
#define TX_TIMEOUT_MS 200U
#define RX_FRAME_TIMEOUT_MS 100U
static UART_HandleTypeDef *screen;
static uint8_t rx_byte, rx_ring[RX_SIZE], tx[TX_SIZE];
static volatile uint32_t rx_head, rx_tail, rx_fault;
static uint32_t last_rx, last_send, tx_started, boot_tick;
static uint32_t running, failed, have_sample, tared, channel, tx_busy;
static uint32_t in_frame, ff_count, payload_left, next_init;
static uint16_t latest[PILOT_CHANNEL_COUNT];
static int16_t temp_raw[2];
static uint32_t temp_tick[2],temp_status[2],temp_seen;

void USART2_IRQHandler(void) {
    if (screen) HAL_UART_IRQHandler(screen);
}
void NextionPilot_RxComplete(UART_HandleTypeDef *uart) {
    if (uart != screen) return;
    uint32_t next = (rx_head + 1U) % RX_SIZE;
    if (next == rx_tail) rx_fault = 1U;
    else { rx_ring[rx_head] = rx_byte; __DMB(); rx_head = next; }
    if (HAL_UART_Receive_IT(screen, &rx_byte, 1) != HAL_OK) rx_fault = 1U;
}
void NextionPilot_Error(UART_HandleTypeDef *uart) {
    if (uart == screen) rx_fault = 1U;
}
void NextionPilot_Init(UART_HandleTypeDef *uart) {
    DisplayMass_Init();
    screen = uart;
    rx_head = rx_tail = rx_fault = 0;
    running = failed = have_sample = tared = channel = tx_busy = 0;
    in_frame = ff_count = payload_left = next_init = 0;
    temp_seen=0;
    boot_tick = last_send = last_rx = HAL_GetTick();
    if (!screen) return;
    HAL_NVIC_SetPriority(USART2_IRQn, 3, 0);
    HAL_NVIC_EnableIRQ(USART2_IRQn);
    if (HAL_UART_Receive_IT(screen, &rx_byte, 1) != HAL_OK) rx_fault = 1U;
}
void NextionPilot_Start(void) {
    DisplayMass_Start();
    running = 1U; failed = have_sample = tared = channel = 0;
    temp_seen=0;
    /* Ignore stale button events from before this session. */
    rx_tail = rx_head; in_frame = ff_count = payload_left = 0;
}
void NextionPilot_Stop(uint32_t fatal_bits) {
    running = 0; failed = fatal_bits;
}
void NextionPilot_Sample(uint32_t seq, const uint16_t *samples, uint32_t flags) {
    /* Called only in foreground with a coherent, immutable queue record. */
    if (!running) return;
    DisplayMass_Add(seq,samples,flags);
    memcpy(latest, samples, sizeof latest);
    have_sample = 1U;
}
void NextionPilot_Temperature(unsigned slot,int16_t raw16,unsigned status){
    if(slot>1)return;
    temp_raw[slot]=raw16;temp_status[slot]=status;temp_tick[slot]=HAL_GetTick();temp_seen|=1U<<slot;
}
static void receive_byte(uint8_t b, uint32_t now) {
    if (now - last_rx > RX_FRAME_TIMEOUT_MS) {
        in_frame = ff_count = payload_left = 0;
    }
    last_rx = now;
    if (in_frame) {
        /* A numeric return may contain FF FF FF or 'T' in its payload. */
        if (payload_left) { --payload_left; return; }
        ff_count = b == 0xff ? ff_count + 1U : 0U;
        if (ff_count == 3U) { in_frame = ff_count = 0; }
        return;
    }
    if (b == 'T') {
        if (running && have_sample) {
            DisplayMass_Zero();
            tared = 1U;
        }
    } else if (b != 0xff && b != '\r' && b != '\n') {
        /* Discard standard Nextion packets; only a standalone legacy T tares.
         * Known fixed payloads are consumed before looking for the terminator. */
        in_frame = 1U; ff_count = 0;
        switch (b) {
        case 0x65: payload_left = 3U; break; /* touch */
        case 0x66: payload_left = 1U; break; /* page */
        case 0x67: case 0x68: payload_left = 5U; break; /* coordinates */
        case 0x71: payload_left = 4U; break; /* number */
        default: payload_left = 0; break; /* status or string */
        }
    }
}
static int begin_tx(unsigned length, uint32_t now) {
    if (HAL_UART_Transmit_IT(screen, tx, (uint16_t)length) != HAL_OK) return 0;
    tx_busy = 1U; tx_started = now;
    return 1;
}
void NextionPilot_Service(void) {
    if (!screen) return;
    uint32_t now = HAL_GetTick();
    if (rx_fault) {
        /* Foreground recovery, independent of PC UART counters/acquisition. */
        HAL_NVIC_DisableIRQ(USART2_IRQn);
        (void)HAL_UART_AbortReceive(screen);
        rx_tail = rx_head; rx_fault = 0;
        in_frame = ff_count = payload_left = 0;
        if (HAL_UART_Receive_IT(screen, &rx_byte, 1) != HAL_OK) rx_fault = 1U;
        HAL_NVIC_EnableIRQ(USART2_IRQn);
    }
    /* Bound work even if the display sends a continuous stream. */
    for (unsigned n = 0; n < 16U && rx_tail != rx_head; ++n) {
        __DMB(); uint8_t b = rx_ring[rx_tail];
        rx_tail = (rx_tail + 1U) % RX_SIZE;
        receive_byte(b, now);
    }
    if (tx_busy) {
        if (screen->gState == HAL_UART_STATE_READY) tx_busy = 0;
        else if (now - tx_started >= TX_TIMEOUT_MS) {
            /* IT only: AbortTransmit does not wait for a DMA transaction. */
            (void)HAL_UART_AbortTransmit(screen); tx_busy = 0;
            next_init = 0; /* Resynchronize after a partially transmitted command. */
        } else return;
    }
    if (now - boot_tick < 1000U || now - last_send < PILOT_NEXTION_PERIOD_MS) return;
    last_send = now;
    if (!next_init) {
        const uint8_t setup[] = {0xff,0xff,0xff,'b','k','c','m','d','=','0',0xff,0xff,0xff};
        memcpy(tx, setup, sizeof setup);
        if (begin_tx(sizeof setup, now)) next_init = 1U;
        return;
    }
    int n;
    if (failed) n = snprintf((char *)tx, sizeof tx, "t0.txt=\"ADC ERROR\"");
    else if (!running) n = snprintf((char *)tx, sizeof tx, "t0.txt=\"%s\"", have_sample ? "STOP" : "WAIT PC");
    else if (!have_sample) n = snprintf((char *)tx, sizeof tx, "t0.txt=\"WAIT ADC\"");
    else {
        char value[24];DisplayMass_Text(value,sizeof value);
        n=snprintf((char *)tx,sizeof tx,"t0.txt=\"%s\"",value);
    }
    if (n < 0 || (unsigned)n + 3U >= sizeof tx) return;
    unsigned length = (unsigned)n;
    memset(tx + length, 0xff, 3); length += 3U;
    if (running && have_sample) {
        uint32_t sum = 0;
        for (unsigned i = 0; i < PILOT_CHANNEL_COUNT; ++i) sum += latest[i];
        /* One existing waveform trace: raw channel mean mapped 0..4095 to 0..255.
         * Display-only scaling; deliberately unchanged by display tare. */
        unsigned value = (unsigned)((sum * 255U) / (PILOT_CHANNEL_COUNT * 4095U));
        n = snprintf((char *)tx + length, sizeof tx - length, "add 2,0,%u", value);
        if (n < 0 || (unsigned)n + length + 3U > sizeof tx) return;
        length += (unsigned)n;
        memset(tx + length, 0xff, 3); length += 3U;
    }
    (void)begin_tx(length, now);
}
