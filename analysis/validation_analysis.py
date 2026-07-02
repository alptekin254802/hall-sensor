#!/usr/bin/env python3
"""Live validation metrics and error plot."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from calibration_model import DEFAULT_OUTPUT_DIR, apply_figure_style, metrics, polish_axes

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_live_validation(path: Path | None = None) -> pd.DataFrame:
    path = path or DATA_DIR / "live_validation_data.csv"
    return pd.read_csv(path)


def plot_live_validation(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    df = load_live_validation()
    mae_g, rmse_g = metrics(df["error_g"])

    fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
    ax.axhline(0, color="black", linewidth=1.0, alpha=0.6)
    ax.plot(
        df["reference_mass_kg"],
        df["error_g"],
        "s-",
        color="#CC79A7",
        linewidth=1.5,
        markersize=3,
        label="Prototype live measurement error",
    )
    ax.axhline(25, color="#D55E00", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.axhline(-25, color="#D55E00", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.set_title("Live Validation Measurement Error")
    ax.set_xlabel("Applied platform mass (kg)")
    ax.set_ylabel("Live measurement deviation (g)")
    ax.text(
        0.97,
        0.92,
        f"MAE: {mae_g:.1f} g\nRMSE: {rmse_g:.1f} g",
        fontsize=7,
        fontweight="bold",
        transform=ax.transAxes,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f9f9f9", edgecolor="gray", alpha=0.85),
    )
    ax.set_xlim(-0.2, 4.2)
    ax.set_ylim(-220, 220)
    polish_axes(ax)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.04), frameon=True)
    fig.tight_layout(rect=[0, 0.14, 1, 1])

    out = output_dir / "Figure_9_live_validation_error.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the live validation measurements.")
    parser.add_argument("--plot", action="store_true", help="Generate the live validation error figure.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    df = load_live_validation()
    mae_g, rmse_g = metrics(df["error_g"])
    print(f"Live validation samples: {len(df)}")
    print(f"Live validation MAE: {mae_g:.2f} g")
    print(f"Live validation RMSE: {rmse_g:.2f} g")
    if args.plot:
        print(f"Live validation figure saved to: {plot_live_validation(args.output_dir)}")


if __name__ == "__main__":
    main()
