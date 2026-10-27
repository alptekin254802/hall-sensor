# Four-channel Hall force head

Bench measurements, frozen calibration models, analysis code and acquisition
firmware accompanying *A modular Hall-effect force-sensing head for algometry:
bench characterization and recalibration after spring exchange*.

The head is a printed spring-magnet assembly developed toward pressure
algometry. One compression spring carries four pairs of NdFeB magnets toward
four fixed UGN3503UA Hall sensors, and an STM32 records the four channels at
100 scans/s. Together, the four outputs give a force estimate and indicate where and
how evenly the load was applied. The spring can be exchanged to change
compliance, and the upper interface is interchangeable.

Main results:

- On 23 placements at 13 masses not used for calibration, four-channel
  interpolation estimated force with an MAE of 0.606 N over the tested central
  range of 0 to 49.03 N.
- Channel averaging gave lower central-force error than any single channel and
  reduced the change caused by off-center loads.
- Channel contrasts followed bench offsets within each position block and
  increased for deliberately tilted and off-center hand presses.
- For both tested springs, three target points including zero recalibrated the
  head to errors similar in magnitude to the original calibration.
- A strain-gauge load cell tested with the same reference loads is included as a
  scalar-accuracy benchmark.

Version **2026.10.21** contains **340 measurement captures**. The reference
loads and their scale check are described under [Reference loads](#reference-loads).

## Reproduce the results

Calibration set A and held-out test set B follow the manuscript.

Use Python 3.11 or newer. The release was checked with Python 3.14 and NumPy 2.3.4.
From this directory:

```sh
python -m pip install -r requirements.txt
python verify_package.py
python reproduce.py
python reproduce_quadratic.py
python reproduce_stability.py
python reproduce_additional.py
python reproduce_channels.py
python reproduce_bootstrap.py
python reproduce_noise.py
python reproduce_revision_checks.py
python reproduce_synchronized.py
python reviewer_response/offset_absolute_errors.py
```

These commands read the included measurements and frozen models. They do not
connect to a device, change the data, or refit the primary calibration.
`verify_package.py` and `reproduce.py` check only the presence of `CITATION.cff`, `LICENSE` and `DATA_LICENSE.md`, whose author names may be masked in anonymous copies; all other integrity checks remain unchanged.
The channel script reconstructs all seven subset fits in memory using the original
A data and checks their B predictions and signed-error correlations. These
additional comparisons were made after the original B evaluation. The quadratic
spring comparator was added after the initial spring-test results were examined.
Recorded resampling settings are in `bootstrap_settings.py`.
The bootstrap script reproduces both primary intervals and paired model-MAE
differences from `analysis/B.json`, preserving the original random generators
and percentile rules. Results are stored in `analysis/bootstrap_intervals.json`.
The noise script checks all 70 complete 10 s windows from the 26 loaded and seven
unloaded comparator B records; its sample-SD range is stored in
`analysis/comparator_noise.json`.

Run `python reproduce_filter_effect.py` to verify `analysis/filter_effect.json`: static B MAE changes and filter-induced differences on the loading branches of the exploratory ramps.

To regenerate the figures, install the optional plotting
dependencies and select an output directory:

```sh
python -m pip install -r requirements-figures.txt
python plot_directional_contrasts.py --output-dir figures
python plot_stability.py --output-dir figures
python plot_synchronized_ramps.py --output-dir figures
```

The scripts recompute the primary calibration and test results, the channel,
quadratic, stability, bootstrap and noise analyses, and the figures listed above.
`reproduce_revision_checks.py` recomputes the checks added during revision
(`analysis/revision_checks.json`): off-center change by channel configuration with
each configuration's own cubic calibration, the 10 s Allan deviation of the unloaded
hold, MLP seed sensitivity, book-cycle unloaded return, local anchor sensitivity and
expected small-addition responses.
`reproduce_synchronized.py` recomputes the hand presses recorded simultaneously with
the load cell, the static control on the same assembly and the exploratory ramps
(`analysis/synchronized_press.json`; specification in `protocols/synchronized_press_plan.json`),
including a post hoc sensitivity with the Hall windows shifted by the median edge lag.
Other figures and some secondary summaries (calibration sensitivity analyses,
position statistics, the thermal regression and comparator repeat summaries) are
provided as precomputed values in `analysis/`.

The separate [`reviewer_response/`](reviewer_response/) folder reproduces the
absolute force-error analysis cited only in Reviewer 4, comment 1 of the response
letter, not in the manuscript. It covers 43 selected D offsets with the frozen
four-channel interpolation and two unloaded references (group `RR_D_zero`, role
`reviewer_response_only`); the manuscript's position analysis remains unchanged.

The main independent test has 23 placements at 13 held-out masses. Its frozen
four-channel model gives MAE 0.606 N and RMSE 0.773 N. The load-cell
comparison uses 21 common placements. The package includes all 15 directional presses in five rounds, 18 manual pairs,
18 synchronized presses, four static-control placements with their unloaded
references and both exploratory ramp records.
The complete tables, ramp figure, methods and setup description are collected in
Hand-loading observations ([HTML](docs/hand_loading_observations.html),
[PDF](docs/hand_loading_observations.pdf)), referenced by
Supplementary Material S7. The manual readings had unverified temporal matching;
the synchronized assembly used an unfastened head on a platform whose deflection
was not measured during acquisition. These comparisons are separate from the
static accuracy benchmark. The preserved plan export describes the intended
mounting; [recording notes](RECORDING_NOTES.md#hand-press-assembly-and-clock-alignment)
describe the actual assembly.

On the common 22 cubic-supported placements, single-channel MAEs range from
1.165 to 2.061 N, pair MAEs from 0.615 to 0.642 N, and the four-channel MAE is
0.629 N. Signed single-channel errors have Pearson correlations of -0.507 for
S1/S3 and -0.818 for S2/S4. Full coverage, metrics and correlation matrices are
in `analysis/channel_comparison.json`. In the position test, the S2-S4 and
S3-S1 contrasts followed the X and Y offsets, respectively (manuscript
Section 3.2).

## Contents

| Directory or file | Contents |
|---|---|
| `raw/` | Losslessly compressed measurement CSVs, grouped by capture ID; `raw/captures.csv` lists all captures |
| `raw_index.json` | Analysis roles, metadata, compressed and original file hashes |
| `analysis/` | Analysis windows, reference capture links, predictions and derived summaries |
| `reviewer_response/` | Reviewer 4, comment 1 analysis and reproduction script; not reported in the manuscript |
| `models/` | Frozen central calibration models and load-cell calibration |
| `force_analysis/` | Calibration model implementations |
| `protocols/` | Exports of the directional and synchronized-press analysis plans |
| `firmware/` | Historical STM32 0.4.0 and 0.5.0 sources/binaries and HX711 Uno sketch |
| `acquisition/` | Optional Hall serial recorder, protocol and readout checks |
| [RECORDING_NOTES.md](RECORDING_NOTES.md) | Recording settings, fixtures, timing alignment and embedded-readout details |
| Hand-loading observations ([HTML](docs/hand_loading_observations.html), [PDF](docs/hand_loading_observations.pdf)) | Complete manual and synchronized tables, static controls, ramp figure and methods |
| `manifest.json` | SHA-256 inventory of the package, excluding the manifest itself |

`data_access.py` opens compressed CSVs directly. The measurement files preserve
original headers and timestamps, including all 1,080,000 samples of the
three-hour unloaded record.

Read [the data dictionary](DATA_DICTIONARY.md) for schemas, units and probe roles,
and [firmware instructions](firmware/README.md) for build and acquisition details.

## Data scope

The package contains the recordings used in the reported analyses. Recordings repeated because of acquisition noise, pilot runs and unreported exploratory series are not included. Analysis windows and unloaded references are defined in analysis/. The reason for excluding one loading-unloading cycle is given in Supplementary Material S5: the book stack was misplaced on the tray. Its records are included as group `C_books_excluded` so that the exclusion value can be checked; they do not enter any reported result. The following cycle used crosswise stacking centered on the tray mark.

## Reference loads

Reference loads were closed containers, books and printed parts, each weighed as
a complete load on a CRW-7024 scale with a 1 g display step. Reported masses are
these uncorrected indications, converted to force with 0.00980665 N/g.

To check this scale, five objects from 99 to 2506 g were weighed three times on
the CRW-7024 and on a CAS CL3000-P retail scale bearing a 2025 verification mark
(5 g interval in this range). The CAS showed the same indication on all three
repetitions, recorded as `cas_g` in
[analysis/reference_scale_check.csv](analysis/reference_scale_check.csv). A
proportional fit to the paired means gave CRW-7024 indications 0.43% higher,
with a maximum absolute residual of 1.7 g.

## Licenses and citation

Original code and documentation: **MIT**. Measurement and derived numerical
data: **CC BY 4.0**. See `DATA_LICENSE.md`, `LICENSE`, `LICENSES/` and
`THIRD_PARTY_NOTICES.md`. Vendor licenses remain attached to their sources.
Use `CITATION.cff` to cite this repository and identify the version used.
