#!/usr/bin/env python3
"""Cached MLP baseline metrics and figures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from calibration_model import DEFAULT_OUTPUT_DIR, apply_figure_style, polish_axes

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_cache(cache_path: Path | None = None, history_path: Path | None = None) -> dict:
    cache_path = cache_path or DATA_DIR / "mlp_baseline_cache.npz"
    history_path = history_path or DATA_DIR / "mlp_training_history.json"
    data = np.load(cache_path)
    history = json.loads(history_path.read_text(encoding="utf-8"))
    return {
        "cal_adc": data["cal_adc"],
        "cal_kg": data["cal_kg"],
        "hyb_41": data["hyb_41"],
        "ai_41": data["ai_41"],
        "h_mae41": float(data["h_mae41"]),
        "a_mae41": float(data["a_mae41"]),
        "h_rmse41": float(data["h_rmse41"]),
        "a_rmse41": float(data["a_rmse41"]),
        "y_real": data["y_real"],
        "hyb_real": data["hyb_real"],
        "ai_real": data["ai_real"],
        "adc_r": data["adc_r"],
        "hyb_c": data["hyb_c"],
        "ai_c": data["ai_c"],
        "m_hyb_mae": float(data["m_hyb_mae"]),
        "m_hyb_rmse": float(data["m_hyb_rmse"]),
        "m_ai_mae": float(data["m_ai_mae"]),
        "m_ai_rmse": float(data["m_ai_rmse"]),
        "n_real": int(data["n_real"]),
        "best_epoch": int(data["best_epoch"]),
        "history": history,
    }


def plot_training_history(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    d = load_cache()
    train_mae_g = np.array(d["history"]["mae"]) * 1000.0
    val_mae_g = np.array(d["history"]["val_mae"]) * 1000.0
    epochs = np.arange(1, len(train_mae_g) + 1)

    fig, ax = plt.subplots(figsize=(3.5, 2.8), dpi=300)
    ax.plot(epochs, train_mae_g, color="#0072B2", linewidth=1.5, label="Training MAE")
    ax.plot(epochs, val_mae_g, color="#D55E00", linewidth=1.5, label="Validation MAE")
    ax.axvline(d["best_epoch"], color="#009E73", linestyle="--", linewidth=1.0, label="Best epoch")
    ax.set_xscale("log")
    ax.set_title("MLP Training and Validation History")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MAE (g)")
    ax.legend(loc="upper right")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_11_mlp_training_history.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_model_curves(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    d = load_cache()

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    ax.plot(d["adc_r"], d["hyb_c"], "-", color="#0072B2", linewidth=1.5, label="Hybrid model")
    ax.plot(d["adc_r"], d["ai_c"], "--", color="#D55E00", linewidth=1.5, label="Edge AI MLP")
    ax.scatter(d["cal_adc"], d["cal_kg"], c="#009E73", s=36, zorder=5, label="Calibration points")
    ax.axvline(128, color="gray", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.axvline(1187, color="gray", linestyle=":", linewidth=1.0, alpha=0.5)
    ax.set_title("Characteristic Calibration Curves: Hybrid Model vs. Edge AI")
    ax.set_xlabel("Fused AVG ADC output (counts)")
    ax.set_ylabel("Mass (kg)")
    ax.set_xlim(-20, 1250)
    ax.set_ylim(-0.1, 4.3)
    ax.legend(loc="lower right")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_12_model_comparison_calibration_curve.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_reference_residuals(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    d = load_cache()
    h_err = (d["hyb_41"] - d["cal_kg"]) * 1000.0
    a_err = (d["ai_41"] - d["cal_kg"]) * 1000.0

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    bar_w = 0.035
    ax.bar(
        d["cal_kg"] - bar_w,
        h_err,
        width=bar_w * 1.8,
        color="#0072B2",
        alpha=0.85,
        label=f"Hybrid (MAE = {d['h_mae41']:.1f} g, RMSE = {d['h_rmse41']:.1f} g)",
    )
    ax.bar(
        d["cal_kg"] + bar_w,
        a_err,
        width=bar_w * 1.8,
        color="#D55E00",
        alpha=0.85,
        label=f"Edge AI (MAE = {d['a_mae41']:.1f} g, RMSE = {d['a_rmse41']:.1f} g)",
    )
    ax.axhline(25, color="gray", linestyle="--", linewidth=1.0, alpha=0.5)
    ax.axhline(-25, color="gray", linestyle="--", linewidth=1.0, alpha=0.5)
    ax.axhline(0, color="black", linewidth=0.5, alpha=0.3)
    ax.set_title("Residual Error at 41 Calibration Reference Points")
    ax.set_xlabel("Reference mass (kg)")
    ax.set_ylabel("Residual error (g)")
    ax.set_xlim(-0.15, 4.15)
    ax.legend(loc="upper right")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_13_model_comparison_residuals.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def plot_plateau_diagnostic(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    apply_figure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    d = load_cache()

    fig, ax = plt.subplots(figsize=(7.0, 4.0), dpi=300)
    ax.scatter(
        d["y_real"],
        (d["hyb_real"] - d["y_real"]) * 1000.0,
        c="#0072B2",
        alpha=0.12,
        s=10,
        rasterized=True,
        label=f"Hybrid (MAE = {d['m_hyb_mae']:.1f} g)",
    )
    ax.scatter(
        d["y_real"],
        (d["ai_real"] - d["y_real"]) * 1000.0,
        c="#D55E00",
        alpha=0.12,
        s=10,
        rasterized=True,
        label=f"Edge AI (MAE = {d['m_ai_mae']:.1f} g)",
    )
    ax.axhline(25, color="gray", linestyle="--", linewidth=1.0, alpha=0.5)
    ax.axhline(-25, color="gray", linestyle="--", linewidth=1.0, alpha=0.5)
    ax.axhline(0, color="black", linewidth=0.5, alpha=0.3)
    ax.set_title(f"Error Distribution on Experimental Plateau Data (n = {d['n_real']})")
    ax.set_xlabel("True mass (kg)")
    ax.set_ylabel("Error (g)")
    ax.set_ylim(-500, 500)
    ax.set_xlim(-0.1, 4.15)
    ax.legend(loc="lower left")
    polish_axes(ax)
    fig.tight_layout()

    out = output_dir / "Figure_14_plateau_diagnostic.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=300)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Report cached MLP baseline metrics.")
    parser.add_argument("--plot", action="store_true", help="Generate MLP comparison figures.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    d = load_cache()
    print("Calibration reference, 41 points")
    print(f"  Hybrid MAE/RMSE: {d['h_mae41']:.2f} g / {d['h_rmse41']:.2f} g")
    print(f"  Edge AI MAE/RMSE: {d['a_mae41']:.2f} g / {d['a_rmse41']:.2f} g")
    print(f"Raw experimental plateau samples: n={d['n_real']}")
    print(f"  Hybrid MAE/RMSE: {d['m_hyb_mae']:.2f} g / {d['m_hyb_rmse']:.2f} g")
    print(f"  Edge AI MAE/RMSE: {d['m_ai_mae']:.2f} g / {d['m_ai_rmse']:.2f} g")
    print(f"Cached best epoch: {d['best_epoch']}")

    if args.plot:
        print(f"Training history saved to: {plot_training_history(args.output_dir)}")
        print(f"Model curves saved to: {plot_model_curves(args.output_dir)}")
        print(f"Reference residuals saved to: {plot_reference_residuals(args.output_dir)}")
        print(f"Plateau diagnostic saved to: {plot_plateau_diagnostic(args.output_dir)}")


if __name__ == "__main__":
    main()
