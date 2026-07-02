#!/usr/bin/env python3
"""Generate manuscript analysis figures from the public data files."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calibration_model import (
    DEFAULT_OUTPUT_DIR,
    apply_figure_style,
    load_calibration_data,
    metrics,
    plot_calibration_curve,
    plot_residuals,
    polish_axes,
)
from hysteresis_analysis import plot_hysteresis
from mlp_baseline import (
    plot_model_curves,
    plot_plateau_diagnostic,
    plot_reference_residuals,
    plot_training_history,
)
from validation_analysis import plot_live_validation

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def plot_ema_response(output_dir: Path) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    alpha = 0.25
    raw = np.r_[np.zeros(10), np.full(45, 1000.0)]
    filtered = np.zeros_like(raw)
    for i, x in enumerate(raw):
        filtered[i] = alpha * x + (1 - alpha) * (filtered[i - 1] if i else x)

    fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
    ax.plot(raw, "--", color="#D55E00", linewidth=1.2, label="Raw step input")
    ax.plot(filtered, "-", color="#009E73", linewidth=1.6, label="EMA output")
    ax.set_title("EMA Filter Response")
    ax.set_xlabel("Sample index")
    ax.set_ylabel("Normalized ADC response")
    ax.legend(loc="lower right")
    polish_axes(ax)
    fig.tight_layout()
    out = output_dir / "Figure_3_ema_filter_response.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_stick_slip(output_dir: Path) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    calibration = load_calibration_data()

    fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
    ax.plot(
        calibration["raw_avg_adc"],
        calibration["reference_mass_kg"],
        "--",
        color="#D55E00",
        linewidth=1.0,
        label="Raw experimental curve",
    )
    ax.plot(
        calibration["corrected_avg_adc"],
        calibration["reference_mass_kg"],
        "o-",
        color="#0072B2",
        markersize=3,
        linewidth=1.5,
        label="Corrected monotonic response",
    )
    ax.set_title("Calibration: Raw vs. Corrected Response")
    ax.set_xlabel("Processed mean differential ADC output (counts)")
    ax.set_ylabel("Reference mass (kg)")
    ax.set_xlim(-50, 1300)
    ax.set_ylim(-0.2, 4.5)
    ax.legend(loc="lower right")
    polish_axes(ax)
    fig.tight_layout()
    out = output_dir / "Figure_4_stick_slip_correction.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_step_response(output_dir: Path) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_DIR / "calibration_plateau_samples.csv")

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    targets = [1000, 2000, 3000, 4000]
    colors = ["#009E73", "#CC79A7", "#E69F00", "#0072B2"]
    for mass_g, color in zip(targets, colors):
        block = df[df["block_grams"] == mass_g].sort_values("sample_in_block")
        ax.plot(
            block["sample_in_block"],
            block["ORT"],
            "-",
            color=color,
            linewidth=1.5,
            label=f"{mass_g / 1000:.2f} kg cycle",
        )
    ax.set_title("Dynamic Step Response and Return-to-Zero Stability")
    ax.set_xlabel("Intra-block sample index")
    ax.set_ylabel("Measured mean ADC output, AVG (counts)")
    ax.set_xlim(-5, 155)
    ax.set_ylim(-50, 1320)
    ax.legend(loc="upper right")
    polish_axes(ax)
    fig.tight_layout()
    out = output_dir / "Figure_5_dynamic_response.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_spatial_fusion(output_dir: Path) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA_DIR / "calibration_plateau_samples.csv")
    df = df[df["block_grams"] <= 4000]
    blocks = np.sort(df["block_grams"].unique())

    s1_offset = float(df[df["block_grams"] == 0]["S1"].mean())
    s2_offset = float(df[df["block_grams"] == 0]["S2"].mean())

    s1_values, s2_values, avg_values, delta_values = [], [], [], []
    for mass_g in blocks:
        block = df[df["block_grams"] == mass_g]
        s1 = float(np.mean(np.abs(block["S1"] - s1_offset)))
        s2 = float(np.mean(np.abs(block["S2"] - s2_offset)))
        s1_values.append(s1)
        s2_values.append(s2)
        avg_values.append((s1 + s2) / 2.0)
        delta_values.append(abs(s1 - s2))

    fig, ax1 = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    kg = blocks / 1000.0
    l1 = ax1.plot(kg, s1_values, "v:", color="#CC79A7", linewidth=1.0, label="Sensor 1")
    l2 = ax1.plot(kg, s2_values, "^:", color="#E69F00", linewidth=1.0, label="Sensor 2")
    l3 = ax1.plot(kg, avg_values, "o-", color="#0072B2", linewidth=1.5, label="AVG fusion signal")
    ax1.set_xlabel("Applied mass (kg)")
    ax1.set_ylabel("Tare-compensated net ADC change")
    ax1.set_xlim(-0.1, 4.1)
    polish_axes(ax1)

    ax2 = ax1.twinx()
    l4 = ax2.plot(kg, delta_values, "s-", color="#D55E00", linewidth=1.5, label="Inter-channel deviation")
    ax2.set_ylabel("Inter-channel spatial deviation", color="#D55E00")
    ax2.tick_params(axis="y", labelcolor="#D55E00")
    ax2.spines["top"].set_visible(False)

    lines = l1 + l2 + l3 + l4
    labels = [line.get_label() for line in lines]
    fig.legend(lines, labels, loc="upper center", bbox_to_anchor=(0.5, 0.84), ncol=2, frameon=True)
    fig.suptitle("Spatial Asymmetry in Dual-Channel Hall Sensor Fusion", fontsize=13, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    out = output_dir / "Figure_8_spatial_fusion_asymmetry.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reproducible analysis figures.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    out = args.output_dir
    generated = [
        plot_ema_response(out),
        plot_stick_slip(out),
        plot_step_response(out),
        plot_residuals(out),
        plot_calibration_curve(out),
        plot_spatial_fusion(out),
        plot_live_validation(out),
        plot_hysteresis(out),
        plot_training_history(out),
        plot_model_curves(out),
        plot_reference_residuals(out),
        plot_plateau_diagnostic(out),
    ]
    print("Generated figures:")
    for path in generated:
        print(f"  {path}")
    print("Figure 1 image panels and Figure 2 hardware block diagram are provided as final manuscript assets.")


if __name__ == "__main__":
    main()
