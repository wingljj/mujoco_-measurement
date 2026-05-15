"""Render MuJoCo cup-transport animations from saved experiment trajectories."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import imageio.v2 as imageio
except ImportError:  # Older imageio releases expose the API at package root.
    import imageio
import mujoco
import numpy as np

try:
    from .kinematics import KukaCupKinematics
except ImportError:  # pragma: no cover - supports direct script execution
    from kinematics import KukaCupKinematics


def read_success_rows(results_csv: Path) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    with results_csv.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["sim_success"].strip().lower() != "true":
                continue
            rows.append(
                {
                    "target_id": int(row["target_id"]),
                    "target": np.array(
                        [float(row["target_x"]), float(row["target_y"]), float(row["target_z"])],
                        dtype=float,
                    ),
                    "final_error_m": float(row["final_error_m"]),
                    "max_tilt_deg": float(row["max_tilt_deg"]),
                    "path_length_m": float(row["path_length_m"]),
                }
            )
    return rows


def choose_targets(rows: List[Dict[str, object]], count: int, mode: str) -> List[Dict[str, object]]:
    if not rows:
        raise RuntimeError("No successful trajectories are available to render.")
    if mode == "longest":
        ordered = sorted(rows, key=lambda row: float(row["path_length_m"]), reverse=True)
    elif mode == "highest-tilt":
        ordered = sorted(rows, key=lambda row: float(row["max_tilt_deg"]), reverse=True)
    else:
        ordered = rows
    return ordered[: min(count, len(ordered))]


def set_target_marker(model: mujoco.MjModel, data: mujoco.MjData, target: np.ndarray) -> None:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "target_marker")
    if body_id < 0:
        return
    mocap_id = model.body_mocapid[body_id]
    if mocap_id >= 0:
        data.mocap_pos[mocap_id] = target


def overlay_status_bar(
    frame: np.ndarray,
    progress: float,
    max_tilt_deg: float,
    final_error_m: float,
    safe_limit_deg: float,
) -> np.ndarray:
    """Add a compact status bar without requiring font rendering."""

    image = frame.copy()
    height, width = image.shape[:2]
    margin = max(8, width // 50)
    bar_width = width - 2 * margin
    y0 = height - margin - 16
    y1 = height - margin
    x0 = margin
    x1 = margin + bar_width

    image[y0:y1, x0:x1] = (25, 28, 35)
    filled = int(np.clip(progress, 0.0, 1.0) * bar_width)
    image[y0:y1, x0 : x0 + filled] = (255, 190, 11)

    tilt_fraction = np.clip(max_tilt_deg / safe_limit_deg, 0.0, 1.0)
    tilt_x = x0 + int(tilt_fraction * bar_width)
    image[y0 - 9 : y1 + 2, max(x0, tilt_x - 2) : min(x1, tilt_x + 2)] = (215, 38, 61)

    err_fraction = np.clip(final_error_m / 0.02, 0.0, 1.0)
    err_width = int(err_fraction * (bar_width // 4))
    image[margin : margin + 8, margin : margin + err_width] = (46, 196, 182)
    return image


def render_single_animation(
    model_path: Path,
    qpos_path: np.ndarray,
    target: np.ndarray,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    camera: str,
    max_tilt_deg: float,
    final_error_m: float,
    safe_limit_deg: float,
    hold_frames: int,
    loop_mode: str,
) -> None:
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    renderer = mujoco.Renderer(model, width=width, height=height)
    kin = KukaCupKinematics(model_path)
    qpos_addr = kin.qpos_addr

    set_target_marker(model, data, target)
    frames = []
    qpos_path = np.asarray(qpos_path, dtype=float)
    if len(qpos_path) == 0:
        raise RuntimeError("Cannot render an empty qpos path.")

    if loop_mode == "pingpong":
        reverse_path = qpos_path[-2:0:-1] if len(qpos_path) > 2 else qpos_path[::-1]
        render_path = np.vstack(
            [
                qpos_path,
                np.repeat(qpos_path[-1][None, :], hold_frames, axis=0),
                reverse_path,
                np.repeat(qpos_path[0][None, :], max(4, hold_frames // 2), axis=0),
            ]
        )
    else:
        render_path = np.vstack(
            [qpos_path, np.repeat(qpos_path[-1][None, :], hold_frames, axis=0)]
        )
    for idx, qpos in enumerate(render_path):
        data.qpos[qpos_addr] = qpos
        data.ctrl[:] = qpos[: model.nu]
        mujoco.mj_forward(model, data)
        renderer.update_scene(data, camera=camera)
        frame = renderer.render()
        progress = idx / max(1, len(render_path) - 1)
        frame = overlay_status_bar(frame, progress, max_tilt_deg, final_error_m, safe_limit_deg)
        frames.append(frame)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    imageio.mimsave(out_path, frames, fps=fps)


def load_planned_qpos(trajectories_path: Path) -> np.ndarray:
    data = np.load(trajectories_path, allow_pickle=True)
    return data["planned_qpos"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="kuka_kr20/kuka_kr20_cup_transport.xml")
    parser.add_argument("--results", default="outputs/experiment_001/results.csv")
    parser.add_argument("--trajectories", default="outputs/experiment_001/trajectories.npz")
    parser.add_argument("--out", default="outputs/animations")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument(
        "--mode",
        choices=["first", "longest", "highest-tilt"],
        default="longest",
        help="Which successful trajectories to render.",
    )
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--camera", default="paper_camera")
    parser.add_argument("--safe-limit-deg", type=float, default=45.0)
    parser.add_argument("--hold-frames", type=int, default=16)
    parser.add_argument(
        "--loop-mode",
        choices=["hold", "pingpong"],
        default="pingpong",
        help="Use pingpong to avoid the visible GIF jump from final pose back to start.",
    )
    parser.add_argument("--format", choices=["gif", "mp4"], default="gif")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    model_path = Path(args.model)
    results_path = Path(args.results)
    trajectories_path = Path(args.trajectories)
    out_dir = Path(args.out)

    rows = choose_targets(read_success_rows(results_path), args.count, args.mode)
    planned_qpos = load_planned_qpos(trajectories_path)

    for rank, row in enumerate(rows, start=1):
        target_id = int(row["target_id"])
        qpos_path = np.asarray(planned_qpos[target_id], dtype=float)
        out_path = out_dir / f"cup_transport_target_{target_id:03d}_{rank:02d}.{args.format}"
        render_single_animation(
            model_path=model_path,
            qpos_path=qpos_path,
            target=row["target"],  # type: ignore[arg-type]
            out_path=out_path,
            width=args.width,
            height=args.height,
            fps=args.fps,
            camera=args.camera,
            max_tilt_deg=float(row["max_tilt_deg"]),
            final_error_m=float(row["final_error_m"]),
            safe_limit_deg=args.safe_limit_deg,
            hold_frames=args.hold_frames,
            loop_mode=args.loop_mode,
        )
        print(
            f"saved {out_path} "
            f"(target_id={target_id}, max_tilt={float(row['max_tilt_deg']):.2f} deg, "
            f"final_error={float(row['final_error_m']) * 1000.0:.1f} mm)"
        )


if __name__ == "__main__":
    main()
