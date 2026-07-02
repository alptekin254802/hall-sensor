/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
uint32_t adc_sensor_1 = 0;
uint32_t adc_sensor_2 = 0;
uint32_t dorf_ortalama_adc = 0;
float hesaplanan_agirlik = 0.0;

float filtreli_agirlik = 0.0f;

uint32_t s1_offset = 0;
uint32_t s2_offset = 0;

typedef struct {
    uint32_t adc_val;
    float weight_kg;
} CalPoint;
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_ADC1_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
void Nextion_Bitir(void);
void Nextion_Yazi_Gonder(char *obj, char *metin);
void Nextion_Grafik_Gonder(char *obj, uint8_t kanal, uint8_t deger);

void ADC_Cift_Kanal_Oku(uint32_t *ch0, uint32_t *ch1);
float Agirlik_Hesapla(uint32_t adc_val);
void Veri_Gonder_UART(uint32_t s1, uint32_t s2, uint32_t ort, float agirlik);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_ADC1_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */

    HAL_Delay(1000);

    uint64_t t1 = 0, t2 = 0;
    for(int i = 0; i < 50; i++) {
        uint32_t s1, s2;
        ADC_Cift_Kanal_Oku(&s1, &s2);
        t1 += s1;
        t2 += s2;
        HAL_Delay(5);
    }
    s1_offset = (uint32_t)(t1 / 50);
    s2_offset = (uint32_t)(t2 / 50);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
	      uint8_t rx_komut = 0;

	      if (HAL_UART_Receive(&huart2, &rx_komut, 1, 1) == HAL_OK)
	      {
	          if (rx_komut == 'T')
	          {
	              Nextion_Yazi_Gonder("t0", "---");

	              uint64_t t1_yeni = 0;
	              uint64_t t2_yeni = 0;

	              for(int i = 0; i < 50; i++) {
	                  uint32_t s1, s2;
	                  ADC_Cift_Kanal_Oku(&s1, &s2);
	                  t1_yeni += s1;
	                  t2_yeni += s2;
	                  HAL_Delay(5);
	              }

	              s1_offset = (uint32_t)(t1_yeni / 50);
	              s2_offset = (uint32_t)(t2_yeni / 50);

	              filtreli_agirlik = 0.0f;

	              Nextion_Yazi_Gonder("t0", "0.00 kg");
	          }
	      }
	          uint64_t s1_toplam = 0;
	          uint64_t s2_toplam = 0;

	          for(int i = 0; i < 32; i++) {
	              uint32_t s1_anlik, s2_anlik;
	              ADC_Cift_Kanal_Oku(&s1_anlik, &s2_anlik);
	              s1_toplam += s1_anlik;
	              s2_toplam += s2_anlik;
	              HAL_Delay(1);
	          }

	          adc_sensor_1 = (uint32_t)(s1_toplam / 32);
	          adc_sensor_2 = (uint32_t)(s2_toplam / 32);

	          int32_t s1_temiz = (int32_t)adc_sensor_1 - (int32_t)s1_offset;
	          int32_t s2_temiz = (int32_t)adc_sensor_2 - (int32_t)s2_offset;
	          dorf_ortalama_adc = (uint32_t)((abs(s1_temiz) + abs(s2_temiz)) / 2);

	          hesaplanan_agirlik = Agirlik_Hesapla(dorf_ortalama_adc);

	          float f_alpha = 0.25f;
	          filtreli_agirlik = (f_alpha * hesaplanan_agirlik) + ((1.0f - f_alpha) * filtreli_agirlik);

	          if (filtreli_agirlik >= 0.50f)
	          {
	              HAL_GPIO_WritePin(KUTLE_LED_GPIO_Port, KUTLE_LED_Pin, GPIO_PIN_SET);
	          }
	          else
	          {
	              HAL_GPIO_WritePin(KUTLE_LED_GPIO_Port, KUTLE_LED_Pin, GPIO_PIN_RESET);
	          }

	          char lcd_buffer[20];
	          sprintf(lcd_buffer, "%.2f kg", filtreli_agirlik);
	          Nextion_Yazi_Gonder("t0", lcd_buffer);

	          float grafik_max_kapasite_kg = 10.0f;
	          float olcekli_grafik = (filtreli_agirlik / grafik_max_kapasite_kg) * 255.0f;

	          if(olcekli_grafik > 255.0f) olcekli_grafik = 255.0f;
	          if(olcekli_grafik < 0.0f)   olcekli_grafik = 0.0f;

	          uint8_t grafik_degeri = (uint8_t)olcekli_grafik;
	          Nextion_Grafik_Gonder("2", 0, grafik_degeri);

	          Veri_Gonder_UART(adc_sensor_1, adc_sensor_2, dorf_ortalama_adc, filtreli_agirlik);

	          HAL_Delay(10);
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc1.Init.ContinuousConvMode = ENABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 2;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_0;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_1;
  sConfig.Rank = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 9600;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(KUTLE_LED_GPIO_Port, KUTLE_LED_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : KUTLE_LED_Pin */
  GPIO_InitStruct.Pin = KUTLE_LED_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(KUTLE_LED_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void Nextion_Bitir(void) {
    uint8_t bitis_kodu[3] = {0xFF, 0xFF, 0xFF};
    HAL_UART_Transmit(&huart2, bitis_kodu, 3, HAL_MAX_DELAY);
}

void Nextion_Yazi_Gonder(char *obj, char *metin) {
    char buffer[60];
    int len = sprintf(buffer, "%s.txt=\"%s\"", obj, metin);
    HAL_UART_Transmit(&huart2, (uint8_t*)buffer, len, HAL_MAX_DELAY);
    Nextion_Bitir();
}

void Nextion_Grafik_Gonder(char *obj, uint8_t kanal, uint8_t deger) {
    char buffer[50];
    int len = sprintf(buffer, "add %s,%d,%d", obj, kanal, deger);
    HAL_UART_Transmit(&huart2, (uint8_t*)buffer, len, HAL_MAX_DELAY);
    Nextion_Bitir();
}
void ADC_Cift_Kanal_Oku(uint32_t *ch0, uint32_t *ch1) {
    ADC_ChannelConfTypeDef sConfig = {0};

    hadc1.Init.ScanConvMode = DISABLE;
    hadc1.Init.NbrOfConversion = 1;
    HAL_ADC_Init(&hadc1);

    sConfig.Channel = ADC_CHANNEL_0;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    sConfig.SamplingTime = ADC_SAMPLETIME_239CYCLES_5;
    HAL_ADC_ConfigChannel(&hadc1, &sConfig);

    HAL_ADC_Start(&hadc1);
    if (HAL_ADC_PollForConversion(&hadc1, 10) == HAL_OK) {
        *ch0 = HAL_ADC_GetValue(&hadc1);
    }
    HAL_ADC_Stop(&hadc1);

    sConfig.Channel = ADC_CHANNEL_1;
    sConfig.Rank = ADC_REGULAR_RANK_1;
    HAL_ADC_ConfigChannel(&hadc1, &sConfig);

    HAL_ADC_Start(&hadc1);
    if (HAL_ADC_PollForConversion(&hadc1, 10) == HAL_OK) {
        *ch1 = HAL_ADC_GetValue(&hadc1);
    }
    HAL_ADC_Stop(&hadc1);
}

float Agirlik_Hesapla(uint32_t adc) {
    if (adc <= 2) {
        return 0.00f;
    }

    if (adc >= 1187) {
        return 4.00f;
    }

    if (adc <= 128) {
        uint32_t lut_adc_low[] = {2, 3, 6, 7, 34, 40, 53, 67, 101, 119, 128};
        float lut_kg_low[]     = {0.0f, 0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f, 0.7f, 0.8f, 0.9f, 1.0f};

        for (int i = 0; i < 10; i++) {
            if (adc >= lut_adc_low[i] && adc <= lut_adc_low[i+1]) {
                float oran = (float)(adc - lut_adc_low[i]) / (float)(lut_adc_low[i+1] - lut_adc_low[i]);
                return lut_kg_low[i] + oran * (lut_kg_low[i+1] - lut_kg_low[i]);
            }
        }
        return 1.00f;
    }

    else {
        float x = (float)adc;
        float hesaplanan = (1.64443979e-9f * x * x * x)
                         - (5.14022513e-6f * x * x)
                         + (7.01235379e-3f * x)
                         + 0.15727274f;

        if (hesaplanan < 0.0f)  return 0.0f;
        if (hesaplanan > 4.0f)  return 4.00f;
        return hesaplanan;
    }
}
void Veri_Gonder_UART(uint32_t s1, uint32_t s2, uint32_t ort, float agirlik) {
    char buffer[100];
    int len = sprintf(buffer, "S1: %lu , S2: %lu , AVG: %lu , kg: %.2f\r\n", s1, s2, ort, agirlik);
    HAL_UART_Transmit(&huart1, (uint8_t*)buffer, len, HAL_MAX_DELAY);
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
