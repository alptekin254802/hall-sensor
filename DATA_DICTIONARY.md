# Data dictionary

Measurement CSVs are stored as `.csv.gz`. Each `raw_index.json` row gives a capture
ID, analysis uses, metadata and a measurement-file map. Each map entry has
the compressed relative path, SHA-256 and byte length, plus the original CSV hash
and byte length. `schemas.json` enumerates every actual header variant.

Hall `s1_adc` through `s4_adc` are signed-channel inputs retained as raw ADC counts;
they are not force readings. Channel responses are unloaded-reference minus
loaded response. `seq` is the device sample sequence and `t_us` is device time in
microseconds. Host timestamps support alignment and are not calibrated aperture
times. Temperature CSVs identify DS18B20 probes by ROM; `temperature_c` is degrees
Celsius and `status == 0` is the valid reading used in the summaries. HX711 ADC
values are signed converter counts. Display files record numerical firmware
outputs and source sequence windows.

## Units and analysis groups

Mass values are grams; force conversion is 0.00980665 N/g. The usual Hall full-span
denominator is 49.03325 N. The common load-cell benchmark denominator is the
4007 g common span (39.29524655 N). Analysis windows are explicit in the reports;
ordinary static means generally use [10,20) seconds. R small-addition summaries
use the final 1000 scans of each recording. Long holds and timed
presses have their own reported windows. Unloaded references are linked by ID.

| Group | Analysis |
|---|---|
| A, B | Source calibration and independent central test |
| A_REFINE | Anchor sensitivity, separate from the primary model |
| C_books | Two analyzed stack cycles, Cycle 1 and Cycle 2 in acquisition order |
| D | Two-axis position experiment |
| E | Repeated loading plateaus and offline filter comparison |
| F | One-hour holds and unloaded return |
| R_small, R_range | Small additions and their bracketing references |
| T | Target-spring calibration and fixed independent test placements |
| H | Strain-gauge load-cell scalar benchmark |
| Nextion, manual_press | Display sequence and 18 manually referenced presses |
| directional_press | Five rounds of center, tilted and marked-offset presses |
| G774, G1000_check | Fixed 774 g thermal cycle and subsequent 1000 g check |
| G_three_hour | Retained three-hour unloaded interval |

The fixed load in G774 is 774 g. Historical acquisition codes such as WATER or BOOK
are identifiers; reference loads as a group comprised closed containers, books
and printed parts.

## Temperature probe locations

| Measurements | Head probe | Ambient probe |
|---|---|---|
| One-hour holds, 15 October | `28a2d27f912506a3`, taped below the sensing region | `28e88f40912506b2`, approximately 1 m away |
| Thermal cycle and three-hour interval | `28128e9900000030`, three-lead sensor beside the Hall carrier | `28e88f40912506b2`, unchanged |

Stability summaries use the first 60 s as
reference, final 60 s as endpoint and complete one-minute means for maximum
deviation. For unloaded records, the N equivalent is minus the raw ADC change
times 0.08611959950625428 N/ADC, the first frozen calibration-segment slope.

## Coverage fields

`total_count` and `total_n` give the number of evaluated placements before
model-domain exclusions; `coverage_n` is the number with a supported prediction.

## Reproduced interval and noise summaries

`analysis/bootstrap_intervals.json` records the original primary mass-group
bootstrap and the paired alternative-minus-interpolation MAE differences.
Both retain placements within their mass group and use 10,000 resamples.
The primary calculation uses NumPy `default_rng` and linear percentiles.
The paired calculation uses Python `random.Random`, a fresh seed per model,
sorted mass groups, `choices`, and sorted draw indices 249 and 9749.

`analysis/comparator_noise.json` lists the 70 complete, non-overlapping 10 s
windows from all 33 comparator B records, including seven unloaded records.
The SD is the within-window sample SD (`ddof=1`) converted through the frozen
load-cell slope to N. The sampling-rate range is limited to the 26 loaded B
records. These SDs do not estimate uncertainty of the averaged force.
