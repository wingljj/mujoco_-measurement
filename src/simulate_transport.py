"""Run batch cup-safe target transport experiments in MuJoCo."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import mujoco
import numpy as np

try:
    from .kinematics import KukaCupKinematics
    from .planner import CupSafePlanner, TrajectoryPlan, path_length
except ImportError:  # pragma: no cover - supports direct script execution
    from kinematics import KukaCupKinematics
    from planner import CupSafePlanner, TrajectoryPlan, path_length


@dataclass
class SimulationConfig:
    model: str
    targets: int
    seed: int
    tilt_limit_deg: float
    position_tolerance: float
    plan_steps: int
    sim_substeps: int
    settle_steps: int


def sample_targets(rng: np.random.Generator, count: int) -> np.ndarray:
    """Sample candidate task points in a front-biased reachable workspace."""

    targets = []
    attempts = 0
    max_attempts = max(500, count * 80)
    while len(targets) < count and attempts < max_attempts:
        attempts += 1
        radius = rng.uniform(0.55, 1.35)
        theta = rng.uniform(-0.78, 0.78)
        height = rng.uniform(0.70, 1.70)
        x = radius * np.cos(theta)
        y = radius * np.sin(theta)
        z = height
        if x < 0.25:
            continue
        targets.append([x, y, z])
    if len(targets) < count:
        raise RuntimeError(f"Only sampled {len(targets)} targets after {attempts} attempts")
    return np.asarray(targets, dtype=float)


def _set_target_marker(model: mujoco.MjModel, data: mujoco.MjData, target: np.ndarray) -> None:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "target_marker")
    if body_id >= 0:
        mocap_id = model.body_mocapid[body_id]
        if mocap_id >= 0:
            data.mocap_pos[mocap_id] = target


def _site_id(model: mujoco.MjModel, site_name: str) -> int:
    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name)
    if site_id < 0:
        raise ValueError(f"Site '{site_name}' not found")
    return site_id


def simulate_plan(
    model_path: str | Path,
    plan: TrajectoryPlan,
    tilt_limit_deg: float,
    position_tolerance: float,
    sim_substeps: int,
    settle_steps: int,
) -> Dict[str, np.ndarray | float | bool]:
    """Track a planned qpos path with MuJoCo position actuators."""

    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)
    kin = KukaCupKinematics(model_path)
    ee_site_id = _site_id(model, "ee_site")
    axis_base_id = _site_id(model, "cup_axis_base_site")
    axis_tip_id = _site_id(model, "cup_axis_tip_site")

    qpos_addr = kin.qpos_addr
    start = plan.qpos[0]
    data.qpos[qpos_addr] = start
    data.ctrl[:] = start[: model.nu]
    _set_target_marker(model, data, plan.target)
    mujoco.mj_forward(model, data)

    ee_history: List[np.ndarray] = []
    tilt_history: List[float] = []
    qpos_history: List[np.ndarray] = []
    ctrl_history: List[np.ndarray] = []
    time_history: List[float] = []

    for desired_qpos in plan.qpos:
        data.ctrl[:] = desired_qpos[: model.nu]
        for _ in range(sim_substeps):
            mujoco.mj_step(model, data)
        _append_state(
            model,
            data,
            ee_site_id,
            axis_base_id,
            axis_tip_id,
            qpos_addr,
            ee_history,
            tilt_history,
            qpos_history,
            ctrl_history,
            time_history,
        )

    final_ctrl = plan.qpos[-1]
    data.ctrl[:] = final_ctrl[: model.nu]
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    _append_state(
        model,
        data,
        ee_site_id,
        axis_base_id,
        axis_tip_id,
        qpos_addr,
        ee_history,
        tilt_history,
        qpos_history,
        ctrl_history,
        time_history,
    )

    ee = np.asarray(ee_history, dtype=float)
    tilt = np.asarray(tilt_history, dtype=float)
    qpos = np.asarray(qpos_history, dtype=float)
    ctrl = np.asarray(ctrl_history, dtype=float)
    times = np.asarray(time_history, dtype=float)
    final_error = float(np.linalg.norm(ee[-1] - plan.target))
    max_tilt = float(np.max(tilt))
    success = bool(final_error <= position_tolerance and max_tilt <= tilt_limit_deg)
    return {
        "success": success,
        "ee_pos": ee,
        "tilt_deg": tilt,
        "qpos": qpos,
        "ctrl": ctrl,
        "time": times,
        "final_error": final_error,
        "max_tilt_deg": max_tilt,
        "path_length": path_length(ee),
    }


def _append_state(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    ee_site_id: int,
    axis_base_id: int,
    axis_tip_id: int,
    qpos_addr: np.ndarray,
    ee_history: List[np.ndarray],
    tilt_history: List[float],
    qpos_history: List[np.ndarray],
    ctrl_history: List[np.ndarray],
    time_history: List[float],
) -> None:
    ee_history.append(data.site_xpos[ee_site_id].copy())
    axis = data.site_xpos[axis_tip_id] - data.site_xpos[axis_base_id]
    axis /= max(np.linalg.norm(axis), 1e-12)
    tilt = float(np.degrees(np.arccos(np.clip(axis[2], -1.0, 1.0))))
    tilt_history.append(tilt)
    qpos_history.append(data.qpos[qpos_addr].copy())
    ctrl_history.append(data.ctrl.copy())
    time_history.append(float(data.time))


def _write_results_csv(rows: List[Dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "target_id",
        "target_x",
        "target_y",
        "target_z",
        "reachable",
        "planned_success",
        "sim_success",
        "final_error_m",
        "planned_error_m",
        "max_tilt_deg",
        "planned_max_tilt_deg",
        "path_length_m",
        "message",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _save_trajectories(
    path: Path,
    targets: np.ndarray,
    planned_qpos: List[np.ndarray],
    planned_ee: List[np.ndarray],
    sim_ee: List[np.ndarray],
    sim_tilt: List[np.ndarray],
    sim_time: List[np.ndarray],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        targets=targets,
        planned_qpos=np.asarray(planned_qpos, dtype=object),
        planned_ee=np.asarray(planned_ee, dtype=object),
        sim_ee=np.asarray(sim_ee, dtype=object),
        sim_tilt=np.asarray(sim_tilt, dtype=object),
        sim_time=np.asarray(sim_time, dtype=object),
    )


def run_experiment(args: argparse.Namespace) -> None:
    model_path = Path(args.model)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    config = SimulationConfig(
        model=str(model_path),
        targets=int(args.targets),
        seed=int(args.seed),
        tilt_limit_deg=float(args.tilt_limit_deg),
        position_tolerance=float(args.position_tolerance),
        plan_steps=int(args.plan_steps),
        sim_substeps=int(args.sim_substeps),
        settle_steps=int(args.settle_steps),
    )

    kin = KukaCupKinematics(model_path)
    planner = CupSafePlanner(
        kin,
        tilt_limit_deg=config.tilt_limit_deg,
        position_tolerance=config.position_tolerance,
    )
    rng = np.random.default_rng(config.seed)
    targets = sample_targets(rng, config.targets)

    rows: List[Dict[str, object]] = []
    planned_qpos: List[np.ndarray] = []
    planned_ee: List[np.ndarray] = []
    sim_ee: List[np.ndarray] = []
    sim_tilt: List[np.ndarray] = []
    sim_time: List[np.ndarray] = []
    start_qpos = kin.default_qpos()

    for target_id, target in enumerate(targets):
        plan = planner.plan_to_target(target, start_qpos=start_qpos, steps=config.plan_steps)
        planned_qpos.append(plan.qpos)
        planned_ee.append(plan.ee_pos)

        if plan.success:
            sim = simulate_plan(
                model_path,
                plan,
                tilt_limit_deg=config.tilt_limit_deg,
                position_tolerance=config.position_tolerance,
                sim_substeps=config.sim_substeps,
                settle_steps=config.settle_steps,
            )
            sim_success = bool(sim["success"])
            final_error = float(sim["final_error"])
            max_tilt = float(sim["max_tilt_deg"])
            sim_ee.append(sim["ee_pos"])  # type: ignore[arg-type]
            sim_tilt.append(sim["tilt_deg"])  # type: ignore[arg-type]
            sim_time.append(sim["time"])  # type: ignore[arg-type]
            sim_path_length = float(sim["path_length"])
        else:
            sim_success = False
            final_error = float("nan")
            max_tilt = float("nan")
            sim_ee.append(np.empty((0, 3)))
            sim_tilt.append(np.empty((0,)))
            sim_time.append(np.empty((0,)))
            sim_path_length = float("nan")

        rows.append(
            {
                "target_id": target_id,
                "target_x": float(target[0]),
                "target_y": float(target[1]),
                "target_z": float(target[2]),
                "reachable": bool(plan.success),
                "planned_success": bool(plan.success),
                "sim_success": sim_success,
                "final_error_m": final_error,
                "planned_error_m": float(plan.final_error),
                "max_tilt_deg": max_tilt,
                "planned_max_tilt_deg": float(plan.max_tilt_deg),
                "path_length_m": sim_path_length,
                "message": plan.message,
            }
        )

        status = "ok" if sim_success else "failed"
        print(
            f"[{target_id + 1:03d}/{config.targets:03d}] {status} "
            f"target=({target[0]:.3f}, {target[1]:.3f}, {target[2]:.3f}) "
            f"err={final_error:.4f} tilt={max_tilt:.2f}"
        )

    _write_results_csv(rows, out_dir / "results.csv")
    _save_trajectories(
        out_dir / "trajectories.npz",
        targets,
        planned_qpos,
        planned_ee,
        sim_ee,
        sim_tilt,
        sim_time,
    )
    with (out_dir / "config.json").open("w", encoding="utf-8") as handle:
        json.dump(asdict(config), handle, indent=2, ensure_ascii=False)

    reachable = sum(1 for row in rows if row["planned_success"])
    succeeded = sum(1 for row in rows if row["sim_success"])
    tracking_failed = sum(
        1 for row in rows if row["planned_success"] and not row["sim_success"]
    )
    success_rate = 100.0 * succeeded / reachable if reachable else 0.0
    print(
        f"Saved {out_dir / 'results.csv'} and {out_dir / 'trajectories.npz'}; "
        f"planned reachable={reachable}/{len(rows)}, "
        f"tracking failures={tracking_failed}, "
        f"simulated success={succeeded}/{reachable} reachable targets "
        f"({success_rate:.1f}%)"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default="kuka_kr20/kuka_kr20_cup_transport.xml",
        help="MuJoCo XML model path.",
    )
    parser.add_argument("--targets", type=int, default=100, help="Number of target samples.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--out", default="outputs/experiment_001", help="Output directory.")
    parser.add_argument("--tilt-limit-deg", type=float, default=45.0)
    parser.add_argument("--position-tolerance", type=float, default=0.02)
    parser.add_argument("--plan-steps", type=int, default=45)
    parser.add_argument("--sim-substeps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=2000)
    return parser


def main() -> None:
    run_experiment(build_parser().parse_args())


if __name__ == "__main__":
    main()
