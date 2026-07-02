#!/usr/bin/env python3
"""Train the Edge-AI MLP baseline and rebuild the cached manuscript arrays.

This script is the cleaned public version of the local Edge-AI cache pipeline.
It trains the 1 -> 32 -> 16 -> 1 MLP from the corrected calibration anchors,
evaluates it against the corrected 41-point reference and retained plateau
samples, and writes the cache files consumed by ``analysis/mlp_baseline.py``.

TensorFlow/Keras is intentionally imported only inside ``train_model`` so the
regular reproduction scripts can run without the training dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

DEFAULT_CACHE_PATH = DATA_DIR / "mlp_baseline_cache.npz"
DEFAULT_HISTORY_PATH = DATA_DIR / "mlp_training_history.json"
DEFAULT_TRAINING_DATA_PATH = DATA_DIR / "mlp_training_data.csv"
DEFAULT_HEADER_PATH = ROOT / "firmware" / "Core" / "Inc" / "nn_model.h"

X_MIN = 0.0
X_MAX = 1207.0
N_AUG = 150
RNG_SEED = 42
DEFAULT_EPOCHS = 1222


def load_calibration(path: Path = DATA_DIR / "calibration_data.csv") -> pd.DataFrame:
    return pd.read_csv(path).sort_values("reference_mass_g").reset_index(drop=True)


def hybrid_model(adc: int | float) -> float:
    adc = int(adc)
    if adc <= 2:
        return 0.0
    if adc >= 1187:
        return 4.0
    if adc <= 128:
        lut_adc = [2, 3, 6, 7, 34, 40, 53, 67, 101, 119, 128]
        lut_kg = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        for i in range(len(lut_adc) - 1):
            if lut_adc[i] <= adc <= lut_adc[i + 1]:
                ratio = (adc - lut_adc[i]) / (lut_adc[i + 1] - lut_adc[i])
                return lut_kg[i] + ratio * (lut_kg[i + 1] - lut_kg[i])
        return 1.0

    x = float(adc)
    result = (
        1.64443979e-9 * x**3
        - 5.14022513e-6 * x**2
        + 7.01235379e-3 * x
        + 0.15727274
    )
    return float(np.clip(result, 0.0, 4.0))


def build_augmented_training_data(calibration: pd.DataFrame, rng: np.random.RandomState) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []

    for anchor_index, row in calibration.iterrows():
        adc_val = float(row["corrected_avg_adc"])
        kg_val = float(row["reference_mass_kg"])
        noise_std = max(2.0, adc_val * 0.05)
        noisy_adc = np.clip(adc_val + rng.normal(0, noise_std, N_AUG), 0, X_MAX)
        for value in noisy_adc:
            rows.append(
                {
                    "anchor_index": int(anchor_index),
                    "reference_mass_kg": kg_val,
                    "augmented_avg_adc": float(value),
                    "normalized_adc": float(value / X_MAX),
                    "noise_std_adc": float(noise_std),
                    "rng_seed": RNG_SEED,
                }
            )

    return pd.DataFrame(rows)


def metrics(error_g: np.ndarray) -> tuple[float, float]:
    return float(np.mean(np.abs(error_g))), float(np.sqrt(np.mean(error_g**2)))


def train_model(x_train, y_train, x_val, y_val, epochs: int):
    os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

    import tensorflow as tf
    from keras import callbacks, layers, models, optimizers

    tf.get_logger().setLevel("ERROR")
    np.random.seed(RNG_SEED)
    tf.random.set_seed(RNG_SEED)

    model = models.Sequential(
        [
            layers.Input(shape=(1,)),
            layers.Dense(32),
            layers.LeakyReLU(negative_slope=0.1),
            layers.Dense(16),
            layers.LeakyReLU(negative_slope=0.1),
            layers.Dense(1),
        ]
    )
    model.compile(optimizer=optimizers.Adam(learning_rate=0.001), loss="mse", metrics=["mae"])

    early_stop = callbacks.EarlyStopping(
        monitor="val_loss", patience=30, restore_best_weights=True
    )
    lr_reduce = callbacks.ReduceLROnPlateau(
        monitor="val_loss", factor=0.5, patience=15, min_lr=1e-6
    )

    history = model.fit(
        x_train,
        y_train,
        epochs=epochs,
        batch_size=64,
        validation_data=(x_val, y_val),
        callbacks=[early_stop, lr_reduce],
        verbose=0,
    )
    return model, history


def predict(model, values: np.ndarray) -> np.ndarray:
    import tensorflow as tf

    scaled = (values.astype(np.float32) / X_MAX).reshape(-1, 1)
    return model(tf.constant(scaled), training=False).numpy().flatten()


def write_c_header(model, output_path: Path, a_mae41: float, a_rmse41: float, m_ai_mae: float, m_ai_rmse: float) -> None:
    from keras import layers

    dense_layers = [layer for layer in model.layers if isinstance(layer, layers.Dense)]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as h:
        h.write("/* ===================================================================== */\n")
        h.write("/* STM32F103 Edge-AI MLP inference baseline                             */\n")
        h.write("/* Architecture: 1 -> 32 (LeakyReLU 0.1) -> 16 (LeakyReLU 0.1) -> 1     */\n")
        h.write(f"/* Calibration-reference MAE/RMSE: {a_mae41:.2f} g / {a_rmse41:.2f} g                    */\n")
        h.write(f"/* Plateau diagnostic MAE/RMSE: {m_ai_mae:.2f} g / {m_ai_rmse:.2f} g                      */\n")
        h.write("/* ===================================================================== */\n\n")
        h.write("#ifndef NN_MODEL_H\n#define NN_MODEL_H\n\n#include <stdint.h>\n\n")
        h.write(f"#define NN_MIN_ADC {X_MIN:.1f}f\n")
        h.write(f"#define NN_MAX_ADC {X_MAX:.1f}f\n\n")

        for idx, layer in enumerate(dense_layers, start=1):
            weights, bias = layer.get_weights()
            flat_weights = weights.flatten()
            h.write(f"static const float NN_W{idx}[{len(flat_weights)}] = {{\n    ")
            h.write(
                ",\n    ".join(
                    ", ".join(f"{value:.6f}f" for value in flat_weights[i : i + 8])
                    for i in range(0, len(flat_weights), 8)
                )
            )
            h.write("\n};\n")
            h.write(f"static const float NN_B{idx}[{len(bias)}] = {{")
            h.write(", ".join(f"{value:.6f}f" for value in bias))
            h.write("};\n\n")

        h.write(
            """
float AI_Agirlik_Tahmin(uint32_t ham_adc) {
    float input = ((float)ham_adc - NN_MIN_ADC) / (NN_MAX_ADC - NN_MIN_ADC);
    if (input < 0.0f) input = 0.0f;
    if (input > 1.0f) input = 1.0f;

    float L1[32];
    for (int i = 0; i < 32; i++) {
        float val = input * NN_W1[i] + NN_B1[i];
        L1[i] = (val > 0.0f) ? val : val * 0.1f;
    }

    float L2[16];
    for (int i = 0; i < 16; i++) {
        float sum = 0.0f;
        for (int j = 0; j < 32; j++) {
            sum += L1[j] * NN_W2[j * 16 + i];
        }
        float val = sum + NN_B2[i];
        L2[i] = (val > 0.0f) ? val : val * 0.1f;
    }

    float kg = 0.0f;
    for (int i = 0; i < 16; i++) {
        kg += L2[i] * NN_W3[i];
    }
    kg += NN_B3[0];

    if (kg < 0.0f) kg = 0.0f;
    if (kg > 4.0f) kg = 4.0f;
    return kg;
}

#endif /* NN_MODEL_H */
"""
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and cache the Edge-AI MLP baseline.")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--history-path", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--training-data-path", type=Path, default=DEFAULT_TRAINING_DATA_PATH)
    parser.add_argument("--header-path", type=Path, default=DEFAULT_HEADER_PATH)
    parser.add_argument("--skip-header", action="store_true", help="Do not regenerate firmware/Core/Inc/nn_model.h.")
    args = parser.parse_args()

    calibration = load_calibration()
    cal_adc = calibration["corrected_avg_adc"].to_numpy(dtype=np.float32)
    cal_kg = calibration["reference_mass_kg"].to_numpy(dtype=np.float32)

    rng = np.random.RandomState(RNG_SEED)
    training_df = build_augmented_training_data(calibration, rng)
    args.training_data_path.parent.mkdir(parents=True, exist_ok=True)
    training_df.to_csv(args.training_data_path, index=False, float_format="%.8f")

    x_aug_scaled = training_df["normalized_adc"].to_numpy(dtype=np.float32)
    y_aug = training_df["reference_mass_kg"].to_numpy(dtype=np.float32)

    shuffle_idx = rng.permutation(len(x_aug_scaled))
    split = int(len(x_aug_scaled) * 0.85)
    x_train = x_aug_scaled[shuffle_idx[:split]]
    x_val = x_aug_scaled[shuffle_idx[split:]]
    y_train = y_aug[shuffle_idx[:split]]
    y_val = y_aug[shuffle_idx[split:]]

    print(f"Calibration anchors: {len(calibration)}")
    print(f"Augmented samples: {len(training_df)}")
    print(f"Train/validation split: {len(x_train)} / {len(x_val)}")
    print(f"Training Edge-AI MLP for up to {args.epochs} epochs...")

    model, history = train_model(x_train, y_train, x_val, y_val, args.epochs)
    best_epoch = int(np.argmin(history.history["val_loss"]) + 1)

    ai_41 = predict(model, cal_adc)
    hyb_41 = np.array([hybrid_model(adc) for adc in cal_adc], dtype=np.float32)

    plateau = pd.read_csv(DATA_DIR / "stable_plateau_samples.csv")
    x_real = plateau["ORT"].to_numpy(dtype=np.float32)
    y_real = plateau["block_kg"].to_numpy(dtype=np.float32)
    ai_real = predict(model, x_real)
    hyb_real = np.array([hybrid_model(adc) for adc in x_real], dtype=np.float32)

    adc_range = np.arange(0, int(X_MAX) + 1, 1, dtype=np.float32)
    ai_curve = predict(model, adc_range)
    hyb_curve = np.array([hybrid_model(adc) for adc in adc_range], dtype=np.float32)

    h_err_41 = (hyb_41 - cal_kg) * 1000.0
    a_err_41 = (ai_41 - cal_kg) * 1000.0
    h_mae41, h_rmse41 = metrics(h_err_41)
    a_mae41, a_rmse41 = metrics(a_err_41)
    m_hyb_mae, m_hyb_rmse = metrics((hyb_real - y_real) * 1000.0)
    m_ai_mae, m_ai_rmse = metrics((ai_real - y_real) * 1000.0)

    args.cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.cache_path,
        cal_adc=cal_adc,
        cal_kg=cal_kg,
        hyb_41=hyb_41,
        ai_41=ai_41,
        h_mae41=h_mae41,
        a_mae41=a_mae41,
        h_rmse41=h_rmse41,
        a_rmse41=a_rmse41,
        y_real=y_real,
        hyb_real=hyb_real,
        ai_real=ai_real,
        adc_r=adc_range,
        hyb_c=hyb_curve,
        ai_c=ai_curve,
        m_hyb_mae=m_hyb_mae,
        m_hyb_rmse=m_hyb_rmse,
        m_ai_mae=m_ai_mae,
        m_ai_rmse=m_ai_rmse,
        n_real=len(y_real),
        x_min=X_MIN,
        x_max=X_MAX,
        best_epoch=best_epoch,
    )
    args.history_path.write_text(
        json.dumps(
            {
                "mae": history.history["mae"],
                "val_mae": history.history["val_mae"],
                "loss": history.history["loss"],
                "val_loss": history.history["val_loss"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if not args.skip_header:
        write_c_header(model, args.header_path, a_mae41, a_rmse41, m_ai_mae, m_ai_rmse)

    print(f"Best epoch: {best_epoch}/{len(history.history['loss'])}")
    print(f"Hybrid calibration MAE/RMSE: {h_mae41:.2f} g / {h_rmse41:.2f} g")
    print(f"Edge-AI calibration MAE/RMSE: {a_mae41:.2f} g / {a_rmse41:.2f} g")
    print(f"Hybrid plateau MAE/RMSE: {m_hyb_mae:.2f} g / {m_hyb_rmse:.2f} g")
    print(f"Edge-AI plateau MAE/RMSE: {m_ai_mae:.2f} g / {m_ai_rmse:.2f} g")
    print(f"Cache written to: {args.cache_path}")
    print(f"History written to: {args.history_path}")
    if not args.skip_header:
        print(f"C header written to: {args.header_path}")


if __name__ == "__main__":
    main()
