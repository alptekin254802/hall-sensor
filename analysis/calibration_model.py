#!/usr/bin/env python3
"""Hybrid calibration model used for the manuscript results."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_OUTPUT_DIR = ROOT / "outputs_tmp" / "generated_figures"

CUBIC_COEFFICIENTS = {
    "a3": 1.64443979e-9,
    "a2": -5.14022513e-6,
    "a1": 7.01235379e-3,
    "a0": 0.15727274,
}


def load_calibration_data(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_DIR / "calibration_data.csv"
    return pd.read_csv(path)


def hybrid_model(adc: float, calibration: pd.DataFrame | None = None) -> float:
    """Return mass in kg from fused AVG ADC counts."""
    if calibration is None:
        calibration = load_calibration_data()

    adc = float(adc)
    if adc <= 2:
        return 0.0
    if adc >= 1187:
        return 4.0

    lut = calibration[calibration["reference_mass_g"] <= 1000]
    lut_adc = lut["corrected_avg_adc"].to_numpy(dtype=float)
    lut_kg = lut["reference_mass_kg"].to_numpy(dtype=float)
    if adc <= 128:
        return float(np.interp(adc, lut_adc, lut_kg))

    x = adc
    result = (
        CUBIC_COEFFICIENTS["a3"] * x**3
        + CUBIC_COEFFICIENTS["a2"] * x**2
        + CUBIC_COEFFICIENTS["a1"] * x
        + CUBIC_COEFFICIENTS["a0"]
    )
    return float(np.clip(result, 0.0, 4.0))


def calibration_residuals(calibration: pd.DataFrame | None = None) -> pd.DataFrame:
    calibration = calibration if calibration is not None else load_calibration_data()
    out = calibration.copy()
    out["predicted_kg"] = [
        hybrid_model(adc, calibration) for adc in out["corrected_avg_adc"]
    ]
    out["error_g"] = (out["predicted_kg"] - out["reference_mass_kg"]) * 1000.0
    return out


def metrics(error_g: np.ndarray | pd.Series) -> tuple[float, float]:
    err = np.asarray(error_g, dtype=float)
    return float(np.mean(np.abs(err))), float(np.sqrt(np.mean(err**2)))


def apply_figure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.titlesize": 13,
            "axes.labelsize": 12,
            "xtick.labelsize": 11,
            "ytick.labelsize": 11,
            "legend.fontsize": 10,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def polish_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(True, which="major", linestyle="-", color="lightgray", alpha=0.3)
    ax.minorticks_on()


def plot_residuals(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    residuals = calibration_residuals()
    mae_g, rmse_g = metrics(residuals["error_g"])

    fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
    ax.axhline(0, color="black", linewidth=1.0, alpha=0.6)
    ax.plot(
        residuals["reference_mass_kg"],
        residuals["error_g"],
        "o-",
        color="#34495e",
        markersize=5,
        linewidth=1.5,
        label="Hybrid model residual error",
    )
    ax.axhline(25, color="#D55E00", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.axhline(-25, color="#D55E00", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.set_title("Residual Error After the Hybrid Model")
    ax.set_xlabel("Reference mass (kg)")
    ax.set_ylabel("Measurement deviation (g)")
    ax.text(
        1.2,
        -75,
        f"MAE: {mae_g:.1f} g\nRMSE: {rmse_g:.1f} g",
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f9f9f9", edgecolor="gray", alpha=0.8),
    )
    ax.set_xlim(-0.1, 4.2)
    ax.set_ylim(-110, 110)
    ax.legend(loc="upper right")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_6_calibration_residual_error.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_calibration_curve(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration = load_calibration_data()
    adc_range = np.linspace(2, 1300, 1000)
    mass_kg = [hybrid_model(adc, calibration) for adc in adc_range]

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    ax.scatter(
        calibration["corrected_avg_adc"],
        calibration["reference_mass_kg"],
        color="#D55E00",
        s=36,
        zorder=5,
        label="Experimental calibration points",
    )
    ax.plot(
        adc_range,
        mass_kg,
        "-",
        color="#0072B2",
        linewidth=1.5,
        label="Multi-region model",
    )
    ax.axvline(128, color="gray", linestyle="--", linewidth=1.0, alpha=0.7)
    ax.axvline(1187, color="gray", linestyle="--", linewidth=1.0, alpha=0.7)
    ax.axhline(4.0, color="black", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.set_title("Characteristic Calibration Curve")
    ax.set_xlabel("Fused AVG ADC output (counts)")
    ax.set_ylabel("Computed mass (kg)")
    ax.text(60, 2.0, "Region I\n0-1 kg LUT", fontsize=9, color="#7f7f7f", ha="center")
    ax.text(650, 2.0, "Region II\n1-4 kg cubic", fontsize=9, color="#0072B2", ha="center")
    ax.text(1240, 2.0, "Safety\nclamp", fontsize=9, color="#009E73", ha="center")
    ax.set_xlim(-30, 1350)
    ax.set_ylim(-0.2, 4.5)
    ax.legend(loc="upper left")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_7_characteristic_calibration_curve.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the hybrid calibration model.")
    parser.add_argument("--plot", action="store_true", help="Generate calibration curve and residual figures.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    residuals = calibration_residuals()
    mae_g, rmse_g = metrics(residuals["error_g"])

    print(f"Calibration anchors: {len(residuals)}")
    print("Calibration range: 0.00-4.00 kg")
    print(f"Hybrid calibration MAE: {mae_g:.2f} g")
    print(f"Hybrid calibration RMSE: {rmse_g:.2f} g")
    print(
        "Cubic coefficients: "
        f"a3={CUBIC_COEFFICIENTS['a3']:.8e}, "
        f"a2={CUBIC_COEFFICIENTS['a2']:.8e}, "
        f"a1={CUBIC_COEFFICIENTS['a1']:.8e}, "
        f"a0={CUBIC_COEFFICIENTS['a0']:.8f}"
    )

    if args.plot:
        print(f"Residual figure saved to: {plot_residuals(args.output_dir)}")
        print(f"Calibration curve saved to: {plot_calibration_curve(args.output_dir)}")


if __name__ == "__main__":
    main()
