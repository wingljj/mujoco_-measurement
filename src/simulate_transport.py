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
    from .kinematics import KukaCupKinematics, smoothstep
    from .planner import CupSafePlanner, TrajectoryPlan, path_length
except ImportError:  # pragma: no cover - supports direct script execution
    from kinematics import KukaCupKinematics, smoothstep
    from planner import CupSafePlanner, TrajectoryPlan, path_length


@dataclass
class SimulationConfig:
    model: str
    targets: int
    seed: int
    method: str
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


def make_planner(method: str, kin: KukaCupKinematics, config: SimulationConfig) -> CupSafePlanner:
    """Create the proposed planner or a baseline planner for comparison."""

    if method == "proposed":
        return CupSafePlanner(
            kin,
            tilt_limit_deg=config.tilt_limit_deg,
            position_tolerance=config.position_tolerance,
            position_weight=7.5,
            tilt_weight=0.90,
            continuity_weight=0.08,
            limit_weight=0.025,
            tilt_barrier_weight=18.0,
        )
    if method in {"position_only", "joint_linear"}:
        return CupSafePlanner(
            kin,
            # Baselines are allowed to solve the position task first; safety is
            # evaluated later with the experiment tilt limit.
            tilt_limit_deg=180.0,
            position_tolerance=config.position_tolerance,
            position_weight=7.5,
            tilt_weight=0.0,
            continuity_weight=0.0,
            limit_weight=0.005,
            tilt_barrier_weight=0.0,
        )
    raise ValueError(f"Unknown planning method: {method}")


def plan_with_method(
    method: str,
    planner: CupSafePlanner,
    kin: KukaCupKinematics,
    target: Iterable[float],
    start_qpos: Iterable[float],
    steps: int,
) -> TrajectoryPlan:
    if method in {"proposed", "position_only"}:
        return planner.plan_to_target(target, start_qpos=start_qpos, steps=steps)
    if method == "joint_linear":
        return plan_joint_linear(planner, kin, target, start_qpos, steps)
    raise ValueError(f"Unknown planning method: {method}")


def plan_joint_linear(
    planner: CupSafePlanner,
    kin: KukaCupKinematics,
    target: Iterable[float],
    start_qpos: Iterable[float],
    steps: int,
) -> TrajectoryPlan:
    """Traditional baseline: solve one target IK and interpolate in joint space."""

    target_array = np.asarray(target, dtype=float)
    start_array = kin.clip(np.asarray(start_qpos, dtype=float))
    ik = planner.solve_ik(target_array, seed_qpos=start_array, max_nfev=200)
    if not ik.success:
        return TrajectoryPlan(
            success=False,
            qpos=np.asarray([start_array], dtype=float),
            ee_pos=np.asarray([kin.state(start_array).ee_pos], dtype=float),
            tilt_deg=np.asarray([kin.state(start_array).tilt_deg], dtype=float),
            target=target_array,
            final_error=float(ik.position_error),
            max_tilt_deg=float(ik.tilt_deg),
            message=f"target IK failed: err={ik.position_error:.4f} m",
        )

    alphas = smoothstep(np.linspace(0.0, 1.0, int(steps)))
    qpos = np.asarray([(1.0 - alpha) * start_array + alpha * ik.qpos for alpha in alphas])
    states = [kin.state(q) for q in qpos]
    ee_pos = np.asarray([state.ee_pos for state in states], dtype=float)
    tilt_deg = np.asarray([state.tilt_deg for state in states], dtype=float)
    final_error = float(np.linalg.norm(ee_pos[-1] - target_array))
    max_tilt = float(np.max(tilt_deg))
    return TrajectoryPlan(
        success=final_error <= planner.position_tolerance,
        qpos=qpos,
        ee_pos=ee_pos,
        tilt_deg=tilt_deg,
        target=target_array,
        final_error=final_error,
        max_tilt_deg=max_tilt,
        message="ok" if final_error <= planner.position_tolerance else "joint interpolation failed",
    )


def smoothness_metrics(qpos: np.ndarray, dt: float) -> Dict[str, float]:
    """Return joint-space smoothness metrics for a planned trajectory."""

    q = np.asarray(qpos, dtype=float)
    if q.ndim != 2 or len(q) < 2:
        return {
            "joint_path_length_rad": float("nan"),
            "mean_joint_step_rad": float("nan"),
            "max_joint_step_rad": float("nan"),
            "rms_joint_speed_rad_s": float("nan"),
            "max_joint_speed_rad_s": float("nan"),
            "rms_joint_accel_rad_s2": float("nan"),
            "max_joint_accel_rad_s2": float("nan"),
        }
    dt = max(float(dt), 1e-9)
    dq = np.diff(q, axis=0)
    step_norm = np.linalg.norm(dq, axis=1)
    speed = dq / dt
    speed_norm = np.linalg.norm(speed, axis=1)
    if len(speed) >= 2:
        accel = np.diff(speed, axis=0) / dt
        accel_norm = np.linalg.norm(accel, axis=1)
        rms_accel = float(np.sqrt(np.mean(accel_norm**2)))
        max_accel = float(np.max(accel_norm))
    else:
        rms_accel = float("nan")
        max_accel = float("nan")
    return {
        "joint_path_length_rad": float(np.sum(step_norm)),
        "mean_joint_step_rad": float(np.mean(step_norm)),
        "max_joint_step_rad": float(np.max(step_norm)),
        "rms_joint_speed_rad_s": float(np.sqrt(np.mean(speed_norm**2))),
        "max_joint_speed_rad_s": float(np.max(speed_norm)),
        "rms_joint_accel_rad_s2": rms_accel,
        "max_joint_accel_rad_s2": max_accel,
    }


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
        "method",
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
        "joint_path_length_rad",
        "mean_joint_step_rad",
        "max_joint_step_rad",
        "rms_joint_speed_rad_s",
        "max_joint_speed_rad_s",
        "rms_joint_accel_rad_s2",
        "max_joint_accel_rad_s2",
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
        method=str(args.method),
        tilt_limit_deg=float(args.tilt_limit_deg),
        position_tolerance=float(args.position_tolerance),
        plan_steps=int(args.plan_steps),
        sim_substeps=int(args.sim_substeps),
        settle_steps=int(args.settle_steps),
    )

    kin = KukaCupKinematics(model_path)
    planner = make_planner(config.method, kin, config)
    rng = np.random.default_rng(config.seed)
    targets = sample_targets(rng, config.targets)
    command_dt = float(kin.model.opt.timestep) * config.sim_substeps

    rows: List[Dict[str, object]] = []
    planned_qpos: List[np.ndarray] = []
    planned_ee: List[np.ndarray] = []
    sim_ee: List[np.ndarray] = []
    sim_tilt: List[np.ndarray] = []
    sim_time: List[np.ndarray] = []
    start_qpos = kin.default_qpos()

    for target_id, target in enumerate(targets):
        plan = plan_with_method(config.method, planner, kin, target, start_qpos, config.plan_steps)
        smoothness = smoothness_metrics(plan.qpos, command_dt)
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
                "method": config.method,
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
                **smoothness,
                "message": plan.message,
            }
        )

        if not args.quiet:
            status = "ok" if sim_success else "failed"
            print(
                f"[{config.method} {target_id + 1:03d}/{config.targets:03d}] {status} "
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
        f"method={config.method}, "
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
    parser.add_argument(
        "--method",
        choices=["proposed", "position_only", "joint_linear"],
        default="proposed",
        help="Planning method used for paper comparison experiments.",
    )
    parser.add_argument("--tilt-limit-deg", type=float, default=45.0)
    parser.add_argument("--position-tolerance", type=float, default=0.02)
    parser.add_argument("--plan-steps", type=int, default=45)
    parser.add_argument("--sim-substeps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=2000)
    parser.add_argument("--quiet", action="store_true", help="Suppress per-target progress lines.")
    return parser


def main() -> None:
    run_experiment(build_parser().parse_args())


if __name__ == "__main__":
    main()
