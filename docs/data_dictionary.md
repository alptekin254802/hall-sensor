# Data Dictionary

All masses are in grams (`g`) or kilograms (`kg`). ADC values are 12-bit STM32 ADC counts after the processing step named in each column.

## `calibration_data.csv`

| Column | Unit | Description |
|---|---:|---|
| `reference_mass_g` | g | Nominal reference mass used for calibration. |
| `reference_mass_kg` | kg | Same mass expressed in kilograms. |
| `raw_avg_adc` | ADC counts | Raw fused AVG ADC anchor before monotonic stick-slip correction. |
| `corrected_avg_adc` | ADC counts | Corrected monotonic AVG ADC anchor used by the LUT/cubic hybrid model. |
| `stick_slip_corrected` | boolean | `true` where the raw anchor was corrected by interpolation. |

## `live_validation_data.csv`

| Column | Unit | Description |
|---|---:|---|
| `reference_mass_kg` | kg | Applied validation mass. |
| `measured_kg` | kg | Displayed live mass from the prototype. |
| `error_g` | g | `(measured_kg - reference_mass_kg) * 1000`. |

## `hysteresis_ramp_data.csv`

| Column | Unit | Description |
|---|---:|---|
| `S1` | ADC counts | Raw ADC reading from Hall sensor 1. |
| `S2` | ADC counts | Raw ADC reading from Hall sensor 2. |
| `ORT` | ADC counts | Original acquisition column for the fused average signal; equivalent to AVG in the paper. |

## `calibration_plateau_samples.csv`

| Column | Unit | Description |
|---|---:|---|
| `idx` | sample index | Global sample index in the acquisition file. |
| `block_grams` | g | Nominal load block. |
| `block_kg` | kg | Nominal load block in kilograms. |
| `sample_in_block` | sample index | Sample index within one load block. |
| `S1` | ADC counts | Raw ADC reading from Hall sensor 1. |
| `S2` | ADC counts | Raw ADC reading from Hall sensor 2. |
| `ORT` | ADC counts | Fused AVG ADC value in the original acquisition naming. |

## `stable_plateau_samples.csv`

Same columns as `calibration_plateau_samples.csv`, after retaining the stable plateau portions used for MLP and plateau diagnostics.

## `mlp_training_data.csv`

| Column | Unit | Description |
|---|---:|---|
| `anchor_index` | index | Calibration anchor index from 0 to 40. |
| `reference_mass_kg` | kg | Target mass for the augmented sample. |
| `augmented_avg_adc` | ADC counts | Gaussian-augmented AVG ADC input. |
| `normalized_adc` | unitless | `augmented_avg_adc / 1207.0`. |
| `noise_std_adc` | ADC counts | Gaussian noise standard deviation used for the anchor. |
| `rng_seed` | integer | Random seed used to generate the deterministic augmentation. |

## Cached MLP Baseline Files

`mlp_baseline_cache.npz` stores cached arrays for the hybrid and MLP model curves, residuals, plateau predictions, and reported metrics. `mlp_training_history.json` stores training and validation loss/MAE histories used for Figure 11.
