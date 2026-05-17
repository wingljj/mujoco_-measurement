"""Summarize actual tilt-limit sweep experiments."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager as fm


POSITION_TOLERANCE_M = 0.02
CHINESE_FONT = fm.FontProperties(fname=r"C:\Windows\Fonts\STSONG.TTF")
LATIN_FONT = fm.FontProperties(fname=r"C:\Windows\Fonts\times.ttf")
COLORS = {
    "blue": "#2F5597",
    "orange": "#C55A11",
    "green": "#548235",
    "red": "#A61C1C",
    "gray": "#666666",
    "purple": "#7030A0",
}


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.serif": ["Times New Roman"],
            "font.sans-serif": ["STSong"],
            "font.size": 8.5,
            "axes.labelsize": 8.5,
            "axes.titlesize": 9.0,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.linewidth": 0.8,
            "grid.linewidth": 0.4,
            "lines.linewidth": 1.35,
            "lines.markersize": 4.2,
            "figure.dpi": 360,
            "savefig.dpi": 360,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "mathtext.fontset": "custom",
            "mathtext.rm": "Times New Roman",
            "mathtext.it": "Times New Roman:italic",
            "mathtext.bf": "Times New Roman:bold",
            "axes.unicode_minus": False,
        }
    )


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def apply_publication_fonts(fig: plt.Figure) -> None:
    for text in fig.findobj(match=mpl.text.Text):
        value = text.get_text()
        if not value:
            continue
        text.set_fontproperties(CHINESE_FONT if has_cjk(value) else LATIN_FONT)
    for ax in fig.axes:
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
        tick_labels = ax.get_xticklabels() + ax.get_yticklabels()
        for tick in tick_labels:
            value = tick.get_text()
            tick.set_fontproperties(CHINESE_FONT if has_cjk(value) else LATIN_FONT)


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def parse_float(value: object) -> float:
    try:
        return float(str(value))
    except ValueError:
        return float("nan")


def read_run(run_dir: Path) -> Dict[str, float]:
    config_path = run_dir / "config.json"
    results_path = run_dir / "results.csv"
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    rows: List[Dict[str, object]] = []
    with results_path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "planned_success": parse_bool(row.get("planned_success", "")),
                    "sim_success": parse_bool(row.get("sim_success", "")),
                    "final_error_m": parse_float(row.get("final_error_m", "nan")),
                    "max_tilt_deg": parse_float(row.get("max_tilt_deg", "nan")),
                    "rms_joint_accel_rad_s2": parse_float(
                        row.get("rms_joint_accel_rad_s2", "nan")
                    ),
                }
            )
    total = len(rows)
    planned = [row for row in rows if bool(row["planned_success"])]
    finite = [row for row in rows if np.isfinite(float(row["final_error_m"]))]
    success = [row for row in rows if bool(row["sim_success"])]
    success_errors = np.asarray([float(row["final_error_m"]) for row in success], dtype=float)
    success_tilts = np.asarray([float(row["max_tilt_deg"]) for row in success], dtype=float)
    planned_accel = np.asarray(
        [float(row["rms_joint_accel_rad_s2"]) for row in planned], dtype=float
    )
    planned_accel = planned_accel[np.isfinite(planned_accel)]
    observed_tilts = np.asarray([float(row["max_tilt_deg"]) for row in finite], dtype=float)
    observed_tilts = observed_tilts[np.isfinite(observed_tilts)]
    return {
        "tilt_limit_deg": float(config["tilt_limit_deg"]),
        "targets": float(total),
        "planned_success": float(len(planned)),
        "sim_success": float(len(success)),
        "success_rate_percent": 100.0 * len(success) / max(1, total),
        "mean_success_error_mm": float(np.mean(success_errors) * 1000.0)
        if len(success_errors)
        else np.nan,
        "max_success_error_mm": float(np.max(success_errors) * 1000.0)
        if len(success_errors)
        else np.nan,
        "max_success_tilt_deg": float(np.max(success_tilts)) if len(success_tilts) else np.nan,
        "max_observed_tilt_deg": float(np.max(observed_tilts)) if len(observed_tilts) else np.nan,
        "median_rms_accel_rad_s2": float(np.median(planned_accel)) if len(planned_accel) else np.nan,
    }


def save_summary(rows: List[Dict[str, float]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "tilt_scan_summary.csv"
    fieldnames = [
        "tilt_limit_deg",
        "targets",
        "planned_success",
        "sim_success",
        "success_rate_percent",
        "mean_success_error_mm",
        "max_success_error_mm",
        "max_success_tilt_deg",
        "max_observed_tilt_deg",
        "median_rms_accel_rad_s2",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {path}")


def plot_scan(rows: List[Dict[str, float]], out_dir: Path) -> None:
    limits = np.asarray([row["tilt_limit_deg"] for row in rows], dtype=float)
    success = np.asarray([row["success_rate_percent"] for row in rows], dtype=float)
    planned = np.asarray([100.0 * row["planned_success"] / row["targets"] for row in rows], dtype=float)
    max_tilt = np.asarray([row["max_success_tilt_deg"] for row in rows], dtype=float)
    accel = np.asarray([row["median_rms_accel_rad_s2"] for row in rows], dtype=float)

    fig, axes = plt.subplots(1, 3, figsize=(8.4, 2.65), facecolor="white")
    axes[0].plot(
        limits,
        success,
        marker="o",
        color=COLORS["blue"],
        linewidth=1.45,
        label="完整成功率",
    )
    axes[0].plot(
        limits,
        planned,
        marker="s",
        color=COLORS["green"],
        linestyle="--",
        linewidth=1.25,
        label="规划成功率",
    )
    axes[0].axhline(float(np.max(success)), color=COLORS["red"], linestyle=(0, (4, 2)), linewidth=1.0)
    axes[0].set_title("（a）成功率变化")
    axes[0].set_ylabel("成功率/%")
    axes[0].set_xlabel("倾角阈值/(°)")
    axes[0].set_ylim(80, 101)
    axes[0].legend(frameon=False, loc="lower right")
    axes[0].grid(True, color="#BFBFBF", alpha=0.35)

    axes[1].plot(limits, max_tilt, marker="o", color=COLORS["orange"], linewidth=1.45)
    axes[1].plot(limits, limits, color=COLORS["gray"], linestyle=":", linewidth=1.0, label="约束边界")
    axes[1].set_title("（b）最大成功倾角")
    axes[1].set_ylabel("倾角/(°)")
    axes[1].set_xlabel("倾角阈值/(°)")
    axes[1].legend(frameon=False, loc="upper left")
    axes[1].grid(True, color="#BFBFBF", alpha=0.35)

    axes[2].plot(limits, accel, marker="o", color=COLORS["purple"], linewidth=1.45)
    axes[2].set_title("（c）关节加速度")
    axes[2].set_ylabel("RMS加速度/(rad·s$^{-2}$)")
    axes[2].set_xlabel("倾角阈值/(°)")
    axes[2].grid(True, color="#BFBFBF", alpha=0.35)

    for ax in axes:
        ax.set_xticks([5, 10, 15, 20, 30, 45])
        ax.tick_params(axis="x", rotation=35)
    apply_publication_fonts(fig)
    fig.tight_layout(w_pad=1.1)
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        path = out_dir / f"tilt_limit_sweep.{ext}"
        fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"saved {path}")
    plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True, help="Run directories with config.json/results.csv.")
    parser.add_argument("--out", default="outputs/paper_runs/tilt_scan_summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_style()
    rows = sorted([read_run(Path(path)) for path in args.runs], key=lambda row: row["tilt_limit_deg"])
    out_dir = Path(args.out)
    save_summary(rows, out_dir)
    plot_scan(rows, out_dir)


if __name__ == "__main__":
    main()
