#!/usr/bin/env python3
"""Dynamic ramp hysteresis analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calibration_model import DEFAULT_OUTPUT_DIR, apply_figure_style, polish_axes

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_hysteresis_data(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_DIR / "hysteresis_ramp_data.csv"
    return pd.read_csv(path)


def hysteresis_metrics(df: pd.DataFrame | None = None) -> dict[str, float | int]:
    df = df if df is not None else load_hysteresis_data()
    adc = df["ORT"].to_numpy(dtype=float)
    peak_index = int(np.argmax(adc))
    loading = adc[: peak_index + 1]
    unloading = adc[peak_index:]

    kg_loading = np.linspace(0.0, 4.0, len(loading))
    kg_unloading = np.linspace(4.0, 0.0, len(unloading))
    common_kg = np.linspace(0.0, 4.0, 100)

    loading_interp = np.interp(common_kg, kg_loading, loading)
    unloading_interp = np.interp(common_kg, kg_unloading[::-1], unloading[::-1])
    gaps = np.abs(loading_interp - unloading_interp)
    max_gap_adc = float(np.max(gaps))
    full_scale_adc = float(np.max(adc) - adc[0])
    max_gap_index = int(np.argmax(gaps))

    return {
        "sample_count": int(len(df)),
        "peak_index": peak_index,
        "max_gap_adc": max_gap_adc,
        "full_scale_adc": full_scale_adc,
        "hysteresis_ratio_percent": float(max_gap_adc / full_scale_adc * 100.0),
        "max_gap_mass_kg": float(common_kg[max_gap_index]),
    }


def plot_hysteresis(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    df = load_hysteresis_data()
    values = hysteresis_metrics(df)
    adc = df["ORT"].to_numpy(dtype=float)
    peak_index = int(values["peak_index"])
    loading = adc[: peak_index + 1]
    unloading = adc[peak_index:]

    kg_loading = np.linspace(0.0, 4.0, len(loading))
    kg_unloading = np.linspace(4.0, 0.0, len(unloading))
    common_kg = np.linspace(0.0, 4.0, 100)
    loading_interp = np.interp(common_kg, kg_loading, loading)
    unloading_interp = np.interp(common_kg, kg_unloading[::-1], unloading[::-1])
    gap_index = int(np.argmax(np.abs(loading_interp - unloading_interp)))

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    ax.axhline(0, color="black", linewidth=1.0, alpha=0.3)
    ax.plot(kg_loading, loading, "-", color="#0072B2", linewidth=1.5, label="Loading ramp")
    ax.plot(kg_unloading, unloading, "--", color="#D55E00", linewidth=1.5, label="Unloading ramp")
    ax.vlines(
        common_kg[gap_index],
        loading_interp[gap_index],
        unloading_interp[gap_index],
        colors="#009E73",
        linewidth=1.5,
        label=f"Maximum gap ({values['max_gap_adc']:.1f} ADC)",
    )
    ax.set_title("Mechanical Hysteresis Loop Under Dynamic Ramping")
    ax.set_xlabel("Nominal mass inferred from time index (kg)")
    ax.set_ylabel("System mean response, AVG ADC (counts)")
    ax.text(
        0.98,
        0.02,
        "Hysteresis report:\n"
        f"Maximum separation: {values['max_gap_adc']:.1f} ADC counts\n"
        f"Net hysteresis error: {values['hysteresis_ratio_percent']:.2f}%",
        fontsize=7,
        fontweight="bold",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f9f9f9", edgecolor="gray", alpha=0.9),
    )
    ax.set_xlim(-0.1, 4.1)
    ax.set_ylim(float(adc[0]) - 50, float(np.max(adc)) + 100)
    ax.legend(loc="upper left")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_10_hysteresis_analysis.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate dynamic ramp hysteresis.")
    parser.add_argument("--plot", action="store_true", help="Generate the hysteresis figure.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    values = hysteresis_metrics()
    print(f"Hysteresis samples: {values['sample_count']}")
    print(f"Maximum hysteresis gap: {values['max_gap_adc']:.2f} ADC")
    print(f"Full-scale ADC span: {values['full_scale_adc']:.2f} ADC")
    print(f"Hysteresis ratio: {values['hysteresis_ratio_percent']:.2f}%")
    if args.plot:
        print(f"Hysteresis figure saved to: {plot_hysteresis(args.output_dir)}")


if __name__ == "__main__":
    main()
