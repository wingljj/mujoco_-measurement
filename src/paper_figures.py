"""Generate additional paper-oriented figures for the cup-safe KR20 study."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib as mpl
import matplotlib.pyplot as plt
import mujoco
import numpy as np
from matplotlib import gridspec
from matplotlib import font_manager as fm
from matplotlib.patches import Circle, FancyArrowPatch, Rectangle

try:
    from .kinematics import KukaCupKinematics
except ImportError:  # pragma: no cover
    from kinematics import KukaCupKinematics


DPI = 360
SAFE_LIMIT_DEG = 45.0
CHINESE_FONT = fm.FontProperties(fname=r"C:\Windows\Fonts\simsun.ttc")
LATIN_FONT = fm.FontProperties(fname=r"C:\Windows\Fonts\times.ttf")


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def apply_figure_fonts(fig: plt.Figure) -> None:
    for text in fig.findobj(match=mpl.text.Text):
        value = text.get_text()
        if not value:
            continue
        text.set_fontproperties(CHINESE_FONT if _has_cjk(value) else LATIN_FONT)
    for ax in fig.axes:
        tick_labels = ax.get_xticklabels() + ax.get_yticklabels()
        if hasattr(ax, "get_zticklabels"):
            tick_labels += ax.get_zticklabels()
        for tick in tick_labels:
            value = tick.get_text()
            tick.set_fontproperties(CHINESE_FONT if _has_cjk(value) else LATIN_FONT)


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "SimSun",
            "font.sans-serif": ["SimSun"],
            "font.size": 9,
            "axes.labelsize": 9,
            "axes.titlesize": 10,
            "legend.fontsize": 8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "axes.linewidth": 0.85,
            "grid.linewidth": 0.45,
            "mathtext.fontset": "custom",
            "mathtext.rm": "Times New Roman",
            "mathtext.it": "Times New Roman:italic",
            "mathtext.bf": "Times New Roman:bold",
            "axes.unicode_minus": False,
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
                    "target": np.array(
                        [float(row["target_x"]), float(row["target_y"]), float(row["target_z"])],
                        dtype=float,
                    ),
                    "reachable": _as_bool(row["planned_success"]),
                    "success": _as_bool(row["sim_success"]),
                    "final_error_m": _float(row["final_error_m"]),
                    "planned_error_m": _float(row["planned_error_m"]),
                    "max_tilt_deg": _float(row["max_tilt_deg"]),
                    "planned_max_tilt_deg": _float(row["planned_max_tilt_deg"]),
                    "path_length_m": _float(row["path_length_m"]),
                }
            )
    return rows


def read_ablation_summary(path: Path) -> List[Dict[str, object]]:
    """Read the ablation rates used by the success dashboard."""
    rows: List[Dict[str, object]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "variant": row["variant"],
                    "sim_rate_pct": float(row["sim_success_of_total_pct"]),
                    "ik_rate_pct": float(row["ik_reachability_pct"]),
                }
            )
    return rows


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def _float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return float("nan")


def load_trajectories(path: Path) -> Dict[str, List[np.ndarray] | np.ndarray]:
    data = np.load(path, allow_pickle=True)
    return {
        "targets": np.asarray(data["targets"], dtype=float),
        "planned_qpos": [np.asarray(item, dtype=float) for item in data["planned_qpos"].tolist()],
        "planned_ee": [np.asarray(item, dtype=float) for item in data["planned_ee"].tolist()],
        "sim_ee": [np.asarray(item, dtype=float) for item in data["sim_ee"].tolist()],
        "sim_tilt": [np.asarray(item, dtype=float) for item in data["sim_tilt"].tolist()],
        "sim_time": [np.asarray(item, dtype=float) for item in data["sim_time"].tolist()],
    }


def save(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    apply_figure_fonts(fig)
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"saved {out_dir / f'{name}.png'} and {out_dir / f'{name}.pdf'}")


def plot_method_overview(out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 3.2), facecolor="white")
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    boxes = [
        (0.04, 0.58, 0.17, 0.24, "可达空间\n目标采样", "#2ec4b6"),
        (0.29, 0.58, 0.17, 0.24, "约束逆运动学\n位置+倾角", "#8338ec"),
        (0.54, 0.58, 0.17, 0.24, "平滑关节\n轨迹生成", "#ffbe0b"),
        (0.79, 0.58, 0.17, 0.24, "MuJoCo伺服\n仿真验证", "#fb5607"),
    ]
    for x, y, w, h, text, color in boxes:
        rect = Rectangle((x, y), w, h, facecolor=color, edgecolor="#1f1f1f", linewidth=1.0, alpha=0.88)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", color="white", weight="bold")
    for idx in range(len(boxes) - 1):
        x0 = boxes[idx][0] + boxes[idx][2] + 0.018
        x1 = boxes[idx + 1][0] - 0.018
        y = boxes[idx][1] + boxes[idx][3] / 2
        arrow = FancyArrowPatch(
            (x0, y),
            (x1, y),
            arrowstyle="-|>",
            mutation_scale=16,
            linewidth=1.4,
            color="#222222",
        )
        ax.add_patch(arrow)

    cup_center = (0.50, 0.27)
    ax.add_patch(Rectangle((cup_center[0] - 0.045, cup_center[1] - 0.10), 0.09, 0.18,
                           facecolor="#bde0fe", edgecolor="#222222", alpha=0.52, linewidth=1.0))
    ax.add_patch(Rectangle((cup_center[0] - 0.038, cup_center[1] - 0.05), 0.076, 0.055,
                           facecolor="#48cae4", edgecolor="none", alpha=0.85))
    ax.plot([cup_center[0], cup_center[0]], [cup_center[1] - 0.11, cup_center[1] + 0.13],
            color="#023e8a", linewidth=2.0, label="杯体轴线")
    ax.plot([cup_center[0], cup_center[0] + 0.13], [cup_center[1] - 0.11, cup_center[1] + 0.04],
            color="#d00000", linewidth=1.8, linestyle="--", label="45°阈值")
    ax.add_patch(Circle((cup_center[0], cup_center[1] - 0.11), 0.012, color="#023e8a"))
    ax.text(0.08, 0.28, r"防洒约束：$\theta=\cos^{-1}(\hat{z}_{cup}\cdot\hat{z}_{world}) \leq 45^\circ$",
            ha="left", va="center", fontsize=11, weight="bold")
    ax.text(0.08, 0.15, "优化目标：最小化末端误差、关节运动量和关节限位接近度",
            ha="left", va="center", color="#333333")
    ax.legend(loc="lower right", frameon=False)
    save(fig, out_dir, "method_pipeline_overview")
    plt.close(fig)


def plot_workspace_multiview(rows: List[Dict[str, object]], out_dir: Path) -> None:
    targets = np.asarray([row["target"] for row in rows], dtype=float)
    success = np.asarray([row["success"] for row in rows], dtype=bool)
    tilt = np.asarray([row["max_tilt_deg"] for row in rows], dtype=float)
    tilt = np.nan_to_num(tilt, nan=SAFE_LIMIT_DEG)

    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.0), facecolor="white")
    views = [
        (0, 1, "俯视图", "X (m)", "Y (m)"),
        (0, 2, "正视图", "X (m)", "Z (m)"),
        (1, 2, "侧视图", "Y (m)", "Z (m)"),
    ]
    for ax, (i, j, title, xlabel, ylabel) in zip(axes, views):
        if np.any(~success):
            ax.scatter(
                targets[~success, i],
                targets[~success, j],
                s=40,
                marker="x",
                color="#d7263d",
                linewidths=1.5,
                label="失败",
            )
        sc = ax.scatter(
            targets[success, i],
            targets[success, j],
            c=tilt[success],
            s=38,
            cmap="turbo",
            vmin=0,
            vmax=SAFE_LIMIT_DEG,
            edgecolors="#111111",
            linewidths=0.25,
            label="成功",
        )
        ax.scatter([0], [0], marker="^", s=75, color="#111111")
        ax.set_title(title, weight="bold")
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.28)
        ax.set_aspect("equal", adjustable="box")
    cbar = fig.colorbar(sc, ax=axes, shrink=0.82, pad=0.02)
    cbar.set_label("最大倾角 (°)")
    save(fig, out_dir, "workspace_multiview_projection")
    plt.close(fig)


def plot_case_study_panel(
    rows: List[Dict[str, object]],
    trajectories: Dict[str, List[np.ndarray] | np.ndarray],
    out_dir: Path,
) -> None:
    success_rows = [row for row in rows if row["success"]]
    case = max(success_rows, key=lambda row: float(row["max_tilt_deg"]))
    target_id = int(case["target_id"])
    sim_ee = trajectories["sim_ee"][target_id]  # type: ignore[index]
    sim_tilt = trajectories["sim_tilt"][target_id]  # type: ignore[index]
    sim_time = trajectories["sim_time"][target_id]  # type: ignore[index]
    qpos = trajectories["planned_qpos"][target_id]  # type: ignore[index]
    target = np.asarray(case["target"], dtype=float)

    fig = plt.figure(figsize=(8.4, 5.6), facecolor="white")
    gs = gridspec.GridSpec(2, 2, width_ratios=[1.2, 1.0], height_ratios=[1.0, 1.0], figure=fig)
    ax3d = fig.add_subplot(gs[:, 0], projection="3d")
    ax_tilt = fig.add_subplot(gs[0, 1])
    ax_q = fig.add_subplot(gs[1, 1])

    pts = np.asarray(sim_ee, dtype=float)
    time_norm = np.linspace(0, 1, len(pts))
    for start, end, c in zip(pts[:-1], pts[1:], mpl.colormaps["plasma"](time_norm[:-1])):
        ax3d.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            [start[2], end[2]],
            color=c,
            linewidth=2.2,
            alpha=0.95,
        )
    ax3d.scatter([pts[0, 0]], [pts[0, 1]], [pts[0, 2]], s=70, color="#2ec4b6", label="起点")
    ax3d.scatter([target[0]], [target[1]], [target[2]], s=110, marker="*", color="#ffbe0b",
                 edgecolors="#111111", linewidths=0.5, label="目标点")
    ax3d.scatter([0], [0], [0], s=100, marker="^", color="#111111", label="基座")
    ax3d.set_title(f"代表性目标 {target_id}", weight="bold")
    ax3d.set_xlabel("X (m)")
    ax3d.set_ylabel("Y (m)")
    ax3d.set_zlabel("Z (m)")
    ax3d.view_init(elev=26, azim=-48)
    ax3d.legend(loc="upper left", frameon=True, framealpha=0.9)

    ax_tilt.plot(sim_time, sim_tilt, color="#8338ec", linewidth=2.0)
    ax_tilt.axhline(SAFE_LIMIT_DEG, color="#d7263d", linestyle="--", linewidth=1.4)
    ax_tilt.fill_between(sim_time, SAFE_LIMIT_DEG, SAFE_LIMIT_DEG + 5, color="#ffccd5", alpha=0.55)
    ax_tilt.set_title("杯体倾角响应", weight="bold")
    ax_tilt.set_xlabel("时间 (s)")
    ax_tilt.set_ylabel("倾角 (°)")
    ax_tilt.set_ylim(0, max(SAFE_LIMIT_DEG + 5, float(np.max(sim_tilt)) + 4))
    ax_tilt.grid(True, alpha=0.30)

    q_time = np.linspace(float(sim_time[0]), float(sim_time[-1]), len(qpos))
    for idx in range(qpos.shape[1]):
        ax_q.plot(q_time, qpos[:, idx], linewidth=1.2, label=f"q{idx + 1}")
    ax_q.set_title("规划关节轨迹", weight="bold")
    ax_q.set_xlabel("时间 (s)")
    ax_q.set_ylabel("关节角 (rad)")
    ax_q.grid(True, alpha=0.30)
    ax_q.legend(ncol=3, frameon=False, fontsize=7)
    fig.tight_layout()
    save(fig, out_dir, "representative_case_study")
    plt.close(fig)


def plot_error_tilt_correlation(rows: List[Dict[str, object]], out_dir: Path) -> None:
    success_rows = [row for row in rows if row["success"]]
    error_mm = np.asarray([float(row["final_error_m"]) * 1000 for row in success_rows], dtype=float)
    tilt = np.asarray([float(row["max_tilt_deg"]) for row in success_rows], dtype=float)
    length = np.asarray([float(row["path_length_m"]) for row in success_rows], dtype=float)

    fig, ax = plt.subplots(figsize=(5.8, 4.4), facecolor="white")
    sc = ax.scatter(
        error_mm,
        tilt,
        c=length,
        cmap="magma",
        s=58,
        edgecolors="#111111",
        linewidths=0.35,
        alpha=0.92,
    )
    ax.axvline(20, color="#d7263d", linestyle="--", linewidth=1.4, label="20 mm阈值")
    ax.axhline(SAFE_LIMIT_DEG, color="#d7263d", linestyle=":", linewidth=1.6, label="45°倾角阈值")
    ax.set_title("跟踪误差与杯体倾角安全裕度", weight="bold")
    ax.set_xlabel("末端最终误差 (mm)")
    ax.set_ylabel("最大杯体倾角 (°)")
    ax.grid(True, alpha=0.30)
    ax.legend(frameon=True, framealpha=0.92)
    cbar = fig.colorbar(sc, ax=ax)
    cbar.set_label("执行路径长度 (m)")
    save(fig, out_dir, "error_tilt_safety_margin")
    plt.close(fig)


def plot_success_metrics_dashboard(
    rows: List[Dict[str, object]],
    ablation_rows: List[Dict[str, object]],
    out_dir: Path,
) -> None:
    errors = np.asarray(
        [
            float(row["final_error_m"]) * 1000
            for row in rows
            if np.isfinite(float(row["final_error_m"]))
        ],
        dtype=float,
    )
    tilts = np.asarray(
        [
            float(row["max_tilt_deg"])
            for row in rows
            if np.isfinite(float(row["max_tilt_deg"]))
        ],
        dtype=float,
    )

    fig = plt.figure(figsize=(8.4, 4.4), facecolor="white")
    gs = gridspec.GridSpec(1, 3, width_ratios=[0.8, 1.0, 1.0], figure=fig)
    ax_rate = fig.add_subplot(gs[0, 0])
    ax_err = fig.add_subplot(gs[0, 1])
    ax_tilt = fig.add_subplot(gs[0, 2])

    label_map = {
        "full_method": "完整方法",
        "no_tilt_barrier": "无倾角屏障",
        "position_only": "纯位置",
        "position_orientation": "位置+姿态",
    }
    display_rows = [row for row in ablation_rows if row["variant"] in label_map]
    labels = [label_map[str(row["variant"])] for row in display_rows]
    rates = [float(row["sim_rate_pct"]) for row in display_rows]
    colors = ["#2ec4b6", "#4c78a8", "#f2b134", "#9c6ade"]
    bars = ax_rate.bar(np.arange(len(rates)), rates, color=colors, edgecolor="#222222", linewidth=0.5)
    ax_rate.set_ylim(0, 105)
    ax_rate.set_ylabel("成功率 (%)")
    ax_rate.set_xticks(np.arange(len(labels)), labels, rotation=28, ha="right")
    ax_rate.set_title("消融仿真成功率", weight="bold")
    ax_rate.grid(axis="y", alpha=0.25)
    for bar, rate in zip(bars, rates):
        ax_rate.text(bar.get_x() + bar.get_width() / 2, rate + 1.2, f"{rate:.1f}%", ha="center", va="bottom", fontsize=7)

    violin = ax_err.violinplot(errors, showmeans=True, showmedians=True)
    _style_violin(violin, "#ffbe0b")
    ax_err.axhline(20, color="#d7263d", linestyle="--", linewidth=1.3)
    ax_err.set_title("最终误差分布", weight="bold")
    ax_err.set_ylabel("误差 (mm)")
    ax_err.set_xticks([])
    ax_err.grid(axis="y", alpha=0.30)

    violin = ax_tilt.violinplot(tilts, showmeans=True, showmedians=True)
    _style_violin(violin, "#8338ec")
    ax_tilt.axhline(SAFE_LIMIT_DEG, color="#d7263d", linestyle="--", linewidth=1.3)
    ax_tilt.set_title("最大倾角分布", weight="bold")
    ax_tilt.set_ylabel("倾角 (°)")
    ax_tilt.set_xticks([])
    ax_tilt.grid(axis="y", alpha=0.30)
    fig.tight_layout()
    save(fig, out_dir, "success_metrics_dashboard")
    plt.close(fig)


def plot_dynamic_metrics(results_path: Path, out_dir: Path) -> None:
    """Plot distributions of the four dynamic proxy metrics."""
    with results_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    fields = [
        ("dyn_max_accel", "最大加速度", "m/s²"),
        ("dyn_max_jerk", "最大 Jerk", "m/s³"),
        ("dyn_max_ang_vel", "最大角速度", "rad/s"),
        ("dyn_avg_ang_vel", "平均角速度", "rad/s"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2), facecolor="white")
    for ax, (field, title, unit), color in zip(
        axes.flat, fields, ["#4c78a8", "#f2b134", "#9c6ade", "#2ec4b6"]
    ):
        values = np.asarray([_float(row[field]) for row in rows], dtype=float)
        values = values[np.isfinite(values)]
        if field == "dyn_max_accel":
            bins = 10
        else:
            bins = np.geomspace(values.min() * 0.9, values.max() * 1.1, 10)
            ax.set_xscale("log")
            ax.xaxis.set_major_formatter(
                mpl.ticker.FuncFormatter(lambda value, _: f"{value:.0e}")
            )
            ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
        ax.hist(values, bins=bins, color=color, edgecolor="white", linewidth=0.7)
        ax.axvline(np.median(values), color="#222222", linestyle="--", linewidth=1.1, label="P50")
        ax.set_title(title, weight="bold")
        ax.set_xlabel(unit)
        ax.set_ylabel("计数")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, out_dir, "fig07_dynamic_metrics")
    plt.close(fig)


def plot_baseline_scatter(
    full_method_path: Path,
    priority_path: Path,
    out_dir: Path,
) -> None:
    """Compare tracking error and maximum tilt for two matched baselines."""
    fig, ax = plt.subplots(figsize=(6.4, 4.8), facecolor="white")
    datasets = [
        (full_method_path, "full_method", "#2ec4b6", "o"),
        (priority_path, "priority_ik", "#9c6ade", "^"),
    ]
    for path, label, color, marker in datasets:
        with path.open("r", newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        x = np.asarray([_float(row["final_error_m"]) * 1000 for row in rows], dtype=float)
        y = np.asarray([_float(row["max_tilt_deg"]) for row in rows], dtype=float)
        finite = np.isfinite(x) & np.isfinite(y)
        ax.scatter(
            x[finite], y[finite], s=24, alpha=0.65, color=color,
            marker=marker, edgecolors="#222222", linewidths=0.35, label=label,
        )
    ax.axvline(20, color="#d7263d", linestyle="--", linewidth=1.2, label="20 mm阈值")
    ax.axhline(SAFE_LIMIT_DEG, color="#d7263d", linestyle=":", linewidth=1.2, label="45°阈值")
    ax.set_xlabel("最终跟踪误差 (mm)")
    ax.set_ylabel("最大杯体倾角 (°)")
    ax.set_title("完整方法与优先级 IK 的跟踪权衡", weight="bold")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, out_dir, "fig08_baseline_comparison")
    plt.close(fig)


def _style_violin(parts: Dict[str, object], color: str) -> None:
    for body in parts["bodies"]:
        body.set_facecolor(color)
        body.set_edgecolor("#111111")
        body.set_alpha(0.72)
    for key in ["cmeans", "cmedians", "cbars", "cmins", "cmaxes"]:
        parts[key].set_color("#111111")
        parts[key].set_linewidth(1.0)


def plot_mujoco_snapshots(
    rows: List[Dict[str, object]],
    trajectories: Dict[str, List[np.ndarray] | np.ndarray],
    model_path: Path,
    out_dir: Path,
) -> None:
    case = max([row for row in rows if row["success"]], key=lambda row: float(row["path_length_m"]))
    target_id = int(case["target_id"])
    qpos = trajectories["planned_qpos"][target_id]  # type: ignore[index]
    target = np.asarray(case["target"], dtype=float)
    frame_ids = np.linspace(0, len(qpos) - 1, 5).astype(int)

    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, width=900, height=650)
    kin = KukaCupKinematics(model_path)
    qpos_addr = kin.qpos_addr
    _set_target_marker(model, data, target)

    images = []
    for frame_id in frame_ids:
        data.qpos[qpos_addr] = qpos[frame_id]
        data.ctrl[:] = qpos[frame_id, : model.nu]
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera="paper_camera")
        images.append(renderer.render())

    fig, axes = plt.subplots(1, len(images), figsize=(10.4, 2.7), facecolor="white")
    for idx, (ax, image, frame_id) in enumerate(zip(axes, images, frame_ids)):
        ax.imshow(image)
        ax.set_axis_off()
        ax.set_title(f"{int(100 * frame_id / max(1, len(qpos) - 1))}%", weight="bold")
        ax.add_patch(Rectangle((0, 0), image.shape[1], image.shape[0], fill=False,
                               edgecolor="#111111", linewidth=1.2))
    fig.suptitle(f"持杯运输渲染快照：目标 {target_id}", weight="bold", y=0.98)
    fig.tight_layout()
    save(fig, out_dir, "rendered_transport_snapshots")
    plt.close(fig)


def _set_target_marker(model: mujoco.MjModel, data: mujoco.MjData, target: np.ndarray) -> None:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "target_marker")
    if body_id < 0:
        return
    mocap_id = model.body_mocapid[body_id]
    if mocap_id >= 0:
        data.mocap_pos[mocap_id] = target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="kuka_kr20/kuka_kr20_cup_transport.xml")
    parser.add_argument("--results", default="outputs/experiment_001/results.csv")
    parser.add_argument("--trajectories", default="outputs/experiment_001/trajectories.npz")
    parser.add_argument("--out", default="outputs/paper_figures")
    parser.add_argument("--ablation-summary", default="outputs/ablation_study/ablation_summary.csv")
    parser.add_argument("--dynamic-results", default="outputs/round2_experiments/dynamic_metrics_results.csv")
    parser.add_argument("--priority-results", default="outputs/external_baselines/priority_ik_results.csv")
    parser.add_argument("--word-out", default="outputs/word_figures")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_style()
    rows = read_results(Path(args.results))
    ablation_rows = read_ablation_summary(Path(args.ablation_summary))
    trajectories = load_trajectories(Path(args.trajectories))
    out_dir = Path(args.out)
    plot_method_overview(out_dir)
    plot_workspace_multiview(rows, out_dir)
    plot_case_study_panel(rows, trajectories, out_dir)
    plot_error_tilt_correlation(rows, out_dir)
    plot_success_metrics_dashboard(rows, ablation_rows, out_dir)
    plot_mujoco_snapshots(rows, trajectories, Path(args.model), out_dir)
    word_out = Path(args.word_out)
    plot_dynamic_metrics(Path(args.dynamic_results), word_out)
    plot_baseline_scatter(
        Path("outputs/ablation_study/full_method_results.csv"),
        Path(args.priority_results),
        word_out,
    )


if __name__ == "__main__":
    main()
