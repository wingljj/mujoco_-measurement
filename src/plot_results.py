"""Create publication-style figures for the KR20 cup transport experiment."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection


FIG_DPI = 360


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.linewidth": 0.9,
            "grid.linewidth": 0.45,
            "lines.linewidth": 1.8,
            "figure.dpi": FIG_DPI,
            "savefig.dpi": FIG_DPI,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def read_results(path: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "target_id": int(row["target_id"]),
                    "target_x": float(row["target_x"]),
                    "target_y": float(row["target_y"]),
                    "target_z": float(row["target_z"]),
                    "reachable": _as_bool(row["reachable"]),
                    "planned_success": _as_bool(row["planned_success"]),
                    "sim_success": _as_bool(row["sim_success"]),
                    "final_error_m": _as_float(row["final_error_m"]),
                    "planned_error_m": _as_float(row["planned_error_m"]),
                    "max_tilt_deg": _as_float(row["max_tilt_deg"]),
                    "planned_max_tilt_deg": _as_float(row["planned_max_tilt_deg"]),
                    "path_length_m": _as_float(row["path_length_m"]),
                    "message": row.get("message", ""),
                }
            )
    return rows


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _as_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("nan")


def _object_array_to_list(values: np.ndarray) -> List[np.ndarray]:
    return [np.asarray(item, dtype=float) for item in values.tolist()]


def load_trajectories(path: Path) -> Dict[str, List[np.ndarray] | np.ndarray]:
    data = np.load(path, allow_pickle=True)
    return {
        "targets": np.asarray(data["targets"], dtype=float),
        "planned_qpos": _object_array_to_list(data["planned_qpos"]),
        "planned_ee": _object_array_to_list(data["planned_ee"]),
        "sim_ee": _object_array_to_list(data["sim_ee"]),
        "sim_tilt": _object_array_to_list(data["sim_tilt"]),
        "sim_time": _object_array_to_list(data["sim_time"]),
    }


def save_figure(fig: plt.Figure, out_dir: Path, stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{stem}.png"
    pdf = out_dir / f"{stem}.pdf"
    fig.savefig(png, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(pdf, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"saved {png} and {pdf}")


def plot_workspace_success(rows: List[Dict[str, object]], out_dir: Path) -> None:
    targets = np.array(
        [[row["target_x"], row["target_y"], row["target_z"]] for row in rows], dtype=float
    )
    success = np.array([row["sim_success"] for row in rows], dtype=bool)
    tilt = np.array([row["max_tilt_deg"] for row in rows], dtype=float)
    tilt_for_color = np.nan_to_num(tilt, nan=45.0)

    fig = plt.figure(figsize=(7.2, 5.8), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_title("Reachable Workspace Success Map", pad=14, fontweight="bold")

    if np.any(~success):
        ax.scatter(
            targets[~success, 0],
            targets[~success, 1],
            targets[~success, 2],
            s=42,
            c="#d7263d",
            marker="x",
            linewidths=1.6,
            label="Failed / rejected",
            depthshade=False,
        )
    scatter = ax.scatter(
        targets[success, 0],
        targets[success, 1],
        targets[success, 2],
        s=58,
        c=tilt_for_color[success],
        cmap="turbo",
        vmin=0,
        vmax=45,
        marker="o",
        edgecolors="black",
        linewidths=0.35,
        label="Cup-safe success",
        depthshade=True,
    )
    ax.scatter([0], [0], [0], s=130, c="#111111", marker="^", label="KR20 base")
    ax.set_xlabel("X position (m)")
    ax.set_ylabel("Y position (m)")
    ax.set_zlabel("Z position (m)")
    ax.view_init(elev=24, azim=-54)
    ax.grid(True, alpha=0.32)
    ax.legend(loc="upper left", frameon=True, framealpha=0.92)
    cbar = fig.colorbar(scatter, ax=ax, shrink=0.72, pad=0.08)
    cbar.set_label("Maximum cup tilt (deg)")
    save_figure(fig, out_dir, "workspace_success_map")
    plt.close(fig)


def plot_tilt_time_series(
    rows: List[Dict[str, object]], trajectories: Dict[str, List[np.ndarray] | np.ndarray], out_dir: Path
) -> None:
    sim_tilt = trajectories["sim_tilt"]  # type: ignore[assignment]
    sim_time = trajectories["sim_time"]  # type: ignore[assignment]
    success_ids = [int(row["target_id"]) for row in rows if row["sim_success"]]

    fig, ax = plt.subplots(figsize=(7.2, 4.2), facecolor="white")
    ax.axhspan(45, 55, color="#ffccd5", alpha=0.45, label="Unsafe region")
    ax.axhline(45, color="#d7263d", linestyle="--", linewidth=1.6, label="45 deg limit")

    if success_ids:
        max_tilts = np.array([rows[idx]["max_tilt_deg"] for idx in success_ids], dtype=float)
        selected = [success_ids[int(np.argmax(max_tilts))]]
        selected.extend(success_ids[: min(4, len(success_ids))])
        selected = list(dict.fromkeys(selected))
    else:
        selected = []

    colors = mpl.colormaps["turbo"](np.linspace(0.10, 0.90, max(len(selected), 1)))
    for color, target_id in zip(colors, selected):
        time = np.asarray(sim_time[target_id], dtype=float)
        tilt = np.asarray(sim_tilt[target_id], dtype=float)
        if len(time) == 0:
            continue
        ax.plot(time, tilt, color=color, alpha=0.95, label=f"Target {target_id}")

    ax.set_title("Cup Tilt During Transport", fontweight="bold")
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Cup tilt angle (deg)")
    ax.set_ylim(0, max(50, _max_finite([row["max_tilt_deg"] for row in rows]) + 6))
    ax.grid(True, alpha=0.35)
    ax.legend(ncol=2, frameon=True, framealpha=0.92)
    save_figure(fig, out_dir, "tilt_time_series")
    plt.close(fig)


def plot_trajectory_3d_render(
    rows: List[Dict[str, object]], trajectories: Dict[str, List[np.ndarray] | np.ndarray], out_dir: Path
) -> None:
    sim_ee = trajectories["sim_ee"]  # type: ignore[assignment]
    targets = np.asarray(trajectories["targets"], dtype=float)
    success_ids = [int(row["target_id"]) for row in rows if row["sim_success"]]

    fig = plt.figure(figsize=(7.2, 5.8), facecolor="#f9fbff")
    ax = fig.add_subplot(111, projection="3d", facecolor="#f9fbff")
    ax.set_title("Cup-Safe End-Effector Transport Trajectories", pad=14, fontweight="bold")

    selected = success_ids[: min(12, len(success_ids))]
    cmap = mpl.colormaps["viridis"]
    for idx, target_id in enumerate(selected):
        pts = np.asarray(sim_ee[target_id], dtype=float)
        if len(pts) < 2:
            continue
        color = cmap(idx / max(1, len(selected) - 1))
        ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color=color, linewidth=2.2, alpha=0.92)
        ax.scatter(
            [pts[-1, 0]],
            [pts[-1, 1]],
            [pts[-1, 2]],
            color=[color],
            s=44,
            edgecolors="white",
            linewidths=0.5,
        )

    if selected:
        ax.scatter(
            targets[selected, 0],
            targets[selected, 1],
            targets[selected, 2],
            s=78,
            c="#ffbe0b",
            marker="*",
            edgecolors="#1f1f1f",
            linewidths=0.4,
            label="Commanded targets",
        )
    ax.scatter([0], [0], [0], s=140, c="#191919", marker="^", label="KR20 base")
    ax.set_xlabel("X position (m)")
    ax.set_ylabel("Y position (m)")
    ax.set_zlabel("Z position (m)")
    ax.view_init(elev=28, azim=-48)
    ax.grid(True, alpha=0.28)
    ax.legend(loc="upper left", frameon=True, framealpha=0.92)
    save_figure(fig, out_dir, "trajectory_3d_render")
    plt.close(fig)


def plot_performance_summary(rows: List[Dict[str, object]], out_dir: Path) -> None:
    success = np.array([row["sim_success"] for row in rows], dtype=bool)
    errors = np.array([row["final_error_m"] for row in rows], dtype=float)
    tilts = np.array([row["max_tilt_deg"] for row in rows], dtype=float)
    lengths = np.array([row["path_length_m"] for row in rows], dtype=float)
    valid_errors = errors[np.isfinite(errors)]
    valid_tilts = tilts[np.isfinite(tilts)]
    valid_lengths = lengths[np.isfinite(lengths)]

    fig, axes = plt.subplots(2, 2, figsize=(7.6, 5.8), facecolor="white")
    ax0, ax1, ax2, ax3 = axes.ravel()
    colors = ["#2ec4b6", "#ff006e", "#8338ec", "#fb5607"]

    ax0.bar(
        ["Success", "Failure"],
        [int(np.sum(success)), int(np.sum(~success))],
        color=[colors[0], "#d7263d"],
        edgecolor="#202020",
        linewidth=0.6,
    )
    ax0.set_title("Task Outcome", fontweight="bold")
    ax0.set_ylabel("Number of targets")
    ax0.grid(axis="y", alpha=0.28)

    _hist_with_stats(ax1, valid_errors * 1000.0, "Final error (mm)", colors[1])
    ax1.axvline(20, color="#d7263d", linestyle="--", linewidth=1.4, label="20 mm limit")
    ax1.legend(frameon=True, framealpha=0.9)

    _hist_with_stats(ax2, valid_tilts, "Maximum tilt (deg)", colors[2])
    ax2.axvline(45, color="#d7263d", linestyle="--", linewidth=1.4, label="45 deg limit")
    ax2.legend(frameon=True, framealpha=0.9)

    _hist_with_stats(ax3, valid_lengths, "Path length (m)", colors[3])
    fig.suptitle("Cup-Safe Transport Performance Summary", fontweight="bold", y=1.01)
    fig.tight_layout()
    save_figure(fig, out_dir, "performance_summary")
    plt.close(fig)


def _hist_with_stats(ax: plt.Axes, values: np.ndarray, xlabel: str, color: str) -> None:
    if len(values) == 0:
        ax.text(0.5, 0.5, "No valid samples", ha="center", va="center", transform=ax.transAxes)
        ax.set_xlabel(xlabel)
        return
    bins = min(12, max(4, len(values)))
    ax.hist(values, bins=bins, color=color, alpha=0.78, edgecolor="white", linewidth=0.8)
    mean = float(np.mean(values))
    ax.axvline(mean, color="#111111", linestyle="-", linewidth=1.2, label=f"mean={mean:.2f}")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.28)


def _max_finite(values: Iterable[object]) -> float:
    array = np.asarray(list(values), dtype=float)
    finite = array[np.isfinite(array)]
    if len(finite) == 0:
        return 0.0
    return float(np.max(finite))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="outputs/experiment_001/results.csv")
    parser.add_argument("--out", default="outputs/figures")
    parser.add_argument(
        "--trajectories",
        default=None,
        help="Optional trajectories.npz path. Defaults to the input CSV directory.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_style()
    input_path = Path(args.input)
    out_dir = Path(args.out)
    trajectory_path = Path(args.trajectories) if args.trajectories else input_path.parent / "trajectories.npz"

    rows = read_results(input_path)
    trajectories = load_trajectories(trajectory_path)
    plot_workspace_success(rows, out_dir)
    plot_tilt_time_series(rows, trajectories, out_dir)
    plot_trajectory_3d_render(rows, trajectories, out_dir)
    plot_performance_summary(rows, out_dir)


if __name__ == "__main__":
    main()
