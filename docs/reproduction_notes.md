# Reproduction Notes

The manuscript figure assets are in `figures/`. The Python scripts write regenerated figures to `outputs_tmp/generated_figures/` by default, so the checked-in manuscript assets are not overwritten accidentally.

## Figures

| Manuscript item | Repository asset | Script | Data source |
|---|---|---|---|
| Fig. 1 | `figures/Figure_1a_pcb_final_implementation.jpg`, `figures/Figure_1b_physical_prototype_views.jpg` | Provided image assets | Prototype photographs |
| Fig. 2 | `figures/Figure_2_hardware_architecture.pdf` | Provided diagram asset | Hardware/pipeline diagram |
| Fig. 3 | `figures/Figure_3_ema_filter_response.pdf` | `analysis/generate_figures.py` | Theoretical EMA step simulation |
| Fig. 4 | `figures/Figure_4_stick_slip_correction.pdf` | `analysis/generate_figures.py` | `data/calibration_data.csv` |
| Fig. 5 | `figures/Figure_5_dynamic_response.pdf` | `analysis/generate_figures.py` | `data/calibration_plateau_samples.csv` |
| Fig. 6 | `figures/Figure_6_calibration_residual_error.pdf` | `analysis/calibration_model.py` | `data/calibration_data.csv` |
| Fig. 7 | `figures/Figure_7_characteristic_calibration_curve.pdf` | `analysis/calibration_model.py` | `data/calibration_data.csv` |
| Fig. 8 | `figures/Figure_8_spatial_fusion_asymmetry.pdf` | `analysis/generate_figures.py` | `data/calibration_plateau_samples.csv` |
| Fig. 9 | `figures/Figure_9_live_validation_error.pdf` | `analysis/validation_analysis.py` | `data/live_validation_data.csv` |
| Fig. 10 | `figures/Figure_10_hysteresis_analysis.pdf` | `analysis/hysteresis_analysis.py` | `data/hysteresis_ramp_data.csv` |
| Fig. 11 | `figures/Figure_11_mlp_training_history.pdf` | `analysis/mlp_baseline.py` | `data/mlp_training_history.json` |
| Fig. 12 | `figures/Figure_12_model_comparison_calibration_curve.pdf` | `analysis/mlp_baseline.py` | `data/mlp_baseline_cache.npz`, `data/calibration_data.csv` |
| Fig. 13 | `figures/Figure_13_model_comparison_residuals.pdf` | `analysis/mlp_baseline.py` | `data/mlp_baseline_cache.npz` |
| Fig. 14 | `figures/Figure_14_plateau_diagnostic.pdf` | `analysis/mlp_baseline.py` | `data/mlp_baseline_cache.npz`, `data/stable_plateau_samples.csv` |

## Tables and Numeric Results

| Result | Script | Data source | Verified value |
|---|---|---|---:|
| Calibration table | n/a | `data/calibration_data.csv` | 41 anchors, 0-4000 g |
| Hybrid calibration residual MAE | `analysis/calibration_model.py` | `data/calibration_data.csv` | 16.71 g |
| Hybrid calibration residual RMSE | `analysis/calibration_model.py` | `data/calibration_data.csv` | 25.70 g |
| Live validation MAE | `analysis/validation_analysis.py` | `data/live_validation_data.csv` | 27.07 g |
| Live validation RMSE | `analysis/validation_analysis.py` | `data/live_validation_data.csv` | 44.97 g |
| Hysteresis maximum gap | `analysis/hysteresis_analysis.py` | `data/hysteresis_ramp_data.csv` | 113.46 ADC |
| Hysteresis ratio | `analysis/hysteresis_analysis.py` | `data/hysteresis_ramp_data.csv` | 9.44% |
| MLP calibration-reference MAE/RMSE | `analysis/mlp_baseline.py` | `data/mlp_baseline_cache.npz` | 27.37 g / 38.65 g |
| MLP plateau diagnostic MAE/RMSE | `analysis/mlp_baseline.py` | `data/mlp_baseline_cache.npz` | 67.03 g / 126.72 g |

The manuscript table reports these metrics rounded to one decimal place (calibration-reference 27.4 g / 38.6 g; plateau 63.8 g / 126.7 g and 67.0 g / 126.7 g for the hybrid and MLP models, respectively), consistent with the script outputs above.
