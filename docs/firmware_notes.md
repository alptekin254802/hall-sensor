# Firmware Notes

## Source Snapshot

The firmware files were copied from:

the local STM32CubeIDE project's `Core` directory

The repository includes the STM32CubeIDE `Core` source snapshot, `stmfinal.ioc`, and the linker script. `Debug/`, `Release/`, object files, map files, ELF/HEX/BIN outputs, and other build artifacts were not copied.

## `main.c`

The active firmware flow is:

1. Initialize HAL, GPIO, ADC1, USART1, and USART2.
2. Wait 1000 ms for display and supply stabilization.
3. Take 50 samples from both Hall channels and store startup tare offsets.
4. Listen for the Nextion `T` command on USART2 to perform live tare.
5. Acquire 32 sequential samples per channel and average them.
6. Subtract the stored offsets and compute the fused AVG signal.
7. Convert AVG ADC counts to mass with the hybrid calibration model.
8. Apply an EMA filter with `alpha = 0.25`.
9. Turn the LED on when the filtered mass is at least 0.50 kg.
10. Update the Nextion display and stream `S1`, `S2`, `AVG`, and `kg` over USART1.

The calibration model in `Agirlik_Hesapla` implements:

- Dead-band output at very low ADC values.
- Region I: 0-1 kg LUT interpolation using 11 corrected calibration anchors.
- Region II: 1-4 kg cubic regression.
- A software clamp at 4.00 kg for `adc >= 1187`.

The code computes the fused ADC signal as `abs(s1_temiz + s2_temiz) / 2`. For the current same-polarity sensor mounting, this matches the manuscript's mean-of-absolute-deflections formulation. If future hardware mounts the sensors with opposite polarities, the fusion expression should be reviewed.

## `nn_model.h`

`nn_model.h` contains a compact pure-C MLP inference function with a `1 -> 32 -> 16 -> 1` topology and Leaky ReLU activations. It accepts fused AVG ADC counts and returns a mass estimate in kg.

In this firmware snapshot, `main.c` does not include `nn_model.h` and does not call `AI_Agirlik_Tahmin`; the active build uses the analytical hybrid model. Treat `nn_model.h` as the edge-AI baseline artifact unless you intentionally create a firmware variant that calls it.

The MLP inference header (`Core/Inc/nn_model.h`) uses an ADC normalization maximum of `NN_MAX_ADC 1207.0f`, matching the final edge-AI model reported in the manuscript. Running its weights on the plateau data reproduces the reported edge-AI figures (41-point MAE 27.6 g; plateau MAE 67.0 g). This header is provided for reproducibility of the on-device inference; the active `main.c` uses the analytical hybrid model and does not call `AI_Agirlik_Tahmin`.

## STM32CubeIDE Project Files

The included `.ioc` and linker script are useful for rebuilding or regenerating the CubeIDE project. The STM32 HAL/CMSIS driver tree was not copied to keep this public repository focused; STM32CubeIDE can regenerate or supply those files. If a fully self-contained build is required, add the driver files with their original ST licenses and keep build outputs ignored.
