"""
Baseline comparison and ablation experiments for cup-safe KR20 transport.
Extends the original planner with configurable ablation modes.
Runs multiple baselines across multiple random seeds.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mujoco
import numpy as np

# Import from project
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kinematics import KukaCupKinematics, RobotState, WORLD_Z, smoothstep
from planner import CupSafePlanner, TrajectoryPlan, path_length

# --- Config ---

@dataclass
class AblationConfig:
    """Which IK residual terms to enable."""
    name: str
    use_position: bool = True
    use_orientation: bool = True
    use_tilt_barrier: bool = True
    use_continuity: bool = True
    use_limit: bool = True
    position_weight: float = 7.5
    orientation_weight: float = 0.90
    tilt_barrier_weight: float = 18.0
    continuity_weight: float = 0.08
    limit_weight: float = 0.025

# Predefined ablation variants
ABLATION_VARIANTS = {
    "full_method": AblationConfig(
        name="full_method",
    ),
    "no_tilt_barrier": AblationConfig(
        name="no_tilt_barrier",
        use_tilt_barrier=False,
    ),
    "position_only": AblationConfig(
        name="position_only",
        use_orientation=False,
        use_tilt_barrier=False,
        use_continuity=False,
        use_limit=False,
    ),
    "position_orientation": AblationConfig(
        name="position_orientation",
        use_tilt_barrier=False,
        use_continuity=False,
        use_limit=False,
    ),
    "no_continuity": AblationConfig(
        name="no_continuity",
        use_continuity=False,
    ),
    "no_limit_centering": AblationConfig(
        name="no_limit_centering",
        use_limit=False,
    ),
    "weak_orientation": AblationConfig(
        name="weak_orientation",
        orientation_weight=0.10,
    ),
    "strong_orientation": AblationConfig(
        name="strong_orientation",
        orientation_weight=3.00,
    ),
    "weak_tilt_barrier": AblationConfig(
        name="weak_tilt_barrier",
        tilt_barrier_weight=5.0,
    ),
    "strong_tilt_barrier": AblationConfig(
        name="strong_tilt_barrier",
        tilt_barrier_weight=50.0,
    ),
    "full_tight10": AblationConfig(
        name="full_tight10",
    ),
    "no_barrier_tight10": AblationConfig(
        name="no_barrier_tight10",
        use_tilt_barrier=False,
    ),
}


class AblationPlanner:
    """Planner that supports configurable ablation of residual terms."""

    def __init__(
        self,
        kin: KukaCupKinematics,
        config: AblationConfig,
        tilt_limit_deg: float = 45.0,
        position_tolerance: float = 0.02,
    ) -> None:
        self.kin = kin
        self.config = config
        self.tilt_limit_deg = float(tilt_limit_deg)
        self.position_tolerance = float(position_tolerance)
        self._tilt_limit_rad = np.radians(self.tilt_limit_deg)

    def solve_ik(
        self,
        target: np.ndarray,
        seed_qpos: Optional[np.ndarray] = None,
        max_nfev: int = 120,
    ) -> dict:
        """Solve IK with only the enabled residual terms."""
        if seed_qpos is None:
            seed = self.kin.default_qpos()
        else:
            seed = self.kin.clip(np.asarray(seed_qpos, dtype=float))

        def residual(qpos: np.ndarray) -> np.ndarray:
            state = self.kin.state(qpos)
            parts = []

            if self.config.use_position:
                parts.append(self.config.position_weight * (state.ee_pos - target))

            if self.config.use_orientation:
                parts.append(self.config.orientation_weight * np.cross(state.cup_axis, WORLD_Z))

            if self.config.use_continuity:
                parts.append(self.config.continuity_weight * (qpos - seed))

            if self.config.use_limit:
                parts.append(self.config.limit_weight * self.kin.normalized_limit_distance(qpos))

            if self.config.use_tilt_barrier:
                tilt_rad = np.radians(state.tilt_deg)
                excess = max(0.0, tilt_rad - self._tilt_limit_rad)
                parts.append(np.array([self.config.tilt_barrier_weight * excess], dtype=float))

            if not parts:
                return np.zeros(0)

            return np.concatenate([np.atleast_1d(p) for p in parts])

        from scipy.optimize import least_squares
        result = least_squares(
            residual,
            seed,
            bounds=(self.kin.lower, self.kin.upper),
            xtol=1e-5,
            ftol=1e-5,
            gtol=1e-5,
            max_nfev=max_nfev,
            verbose=0,
        )
        state = self.kin.state(result.x)
        position_error = float(np.linalg.norm(state.ee_pos - target))
        success = bool(
            result.success
            and position_error <= self.position_tolerance
            and state.tilt_deg <= self.tilt_limit_deg
        )
        return {
            "success": success,
            "qpos": self.kin.clip(result.x),
            "ee_pos": state.ee_pos,
            "tilt_deg": state.tilt_deg,
            "position_error": position_error,
            "cost": float(result.cost),
            "nfev": int(result.nfev),
            "message": str(result.message),
        }

    def plan_to_target(
        self,
        target: np.ndarray,
        start_qpos: Optional[np.ndarray] = None,
        steps: int = 45,
    ) -> dict:
        if start_qpos is None:
            start_qpos = self.kin.default_qpos()

        start_state = self.kin.state(start_qpos)
        t_values = smoothstep(np.linspace(0.0, 1.0, int(steps)))

        qpos_path = []
        ee_path = []
        tilt_path = []
        nfev_total = 0
        seed = np.asarray(start_qpos, dtype=float).copy()
        all_success = True
        failure_msg = "ok"

        for alpha in t_values:
            waypoint = (1.0 - alpha) * start_state.ee_pos + alpha * target
            ik = self.solve_ik(waypoint, seed_qpos=seed)
            qpos_path.append(ik["qpos"])
            ee_path.append(ik["ee_pos"])
            tilt_path.append(ik["tilt_deg"])
            nfev_total += ik["nfev"]
            seed = ik["qpos"]

            if not ik["success"]:
                all_success = False
                failure_msg = (
                    f"waypoint failed: err={ik['position_error']:.4f}m, "
                    f"tilt={ik['tilt_deg']:.2f}deg"
                )
                break

        qpos = np.asarray(qpos_path, dtype=float)
        ee_pos = np.asarray(ee_path, dtype=float)
        tilt_deg_arr = np.asarray(tilt_path, dtype=float)

        final_error = (
            float(np.linalg.norm(ee_pos[-1] - target)) if len(ee_pos) else float("inf")
        )
        max_tilt = float(np.max(tilt_deg_arr)) if len(tilt_deg_arr) else float("inf")
        success = bool(
            len(qpos_path) == len(t_values)
            and final_error <= self.position_tolerance
            and max_tilt <= self.tilt_limit_deg
        )

        return {
            "success": success,
            "qpos": qpos,
            "ee_pos": ee_pos,
            "tilt_deg": tilt_deg_arr,
            "target": target,
            "final_error": final_error,
            "max_tilt_deg": max_tilt,
            "nfev_total": nfev_total,
            "message": failure_msg if not success else "ok",
        }


def sample_targets(rng: np.random.Generator, count: int) -> np.ndarray:
    """Same target sampling as original."""
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


def simulate_plan(
    model_path: Path,
    plan: dict,
    tilt_limit_deg: float,
    position_tolerance: float,
    sim_substeps: int,
    settle_steps: int,
    kin: KukaCupKinematics,
) -> dict:
    """Track planned qpos path with MuJoCo (same as original)."""
    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)

    ee_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "ee_site")
    axis_base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "cup_axis_base_site")
    axis_tip_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "cup_axis_tip_site")
    qpos_addr = kin.qpos_addr

    planned_qpos = np.asarray(plan["qpos"], dtype=float)
    target = np.asarray(plan["target"], dtype=float)

    data.qpos[qpos_addr] = planned_qpos[0]
    data.ctrl[:] = planned_qpos[0, :model.nu]

    # Set target marker
    marker_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "target_marker")
    if marker_id >= 0:
        mocap_id = model.body_mocapid[marker_id]
        if mocap_id >= 0:
            data.mocap_pos[mocap_id] = target

    mujoco.mj_forward(model, data)

    ee_history = []
    tilt_history = []

    for desired_qpos in planned_qpos:
        data.ctrl[:] = desired_qpos[:model.nu]
        for _ in range(sim_substeps):
            mujoco.mj_step(model, data)
        ee_history.append(data.site_xpos[ee_site_id].copy())
        axis = data.site_xpos[axis_tip_id] - data.site_xpos[axis_base_id]
        axis /= max(np.linalg.norm(axis), 1e-12)
        tilt = float(np.degrees(np.arccos(np.clip(axis[2], -1.0, 1.0))))
        tilt_history.append(tilt)

    # Settle
    data.ctrl[:] = planned_qpos[-1, :model.nu]
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    ee_history.append(data.site_xpos[ee_site_id].copy())
    axis = data.site_xpos[axis_tip_id] - data.site_xpos[axis_base_id]
    axis /= max(np.linalg.norm(axis), 1e-12)
    tilt = float(np.degrees(np.arccos(np.clip(axis[2], -1.0, 1.0))))
    tilt_history.append(tilt)

    ee = np.asarray(ee_history)
    tilt_arr = np.asarray(tilt_history)
    final_error = float(np.linalg.norm(ee[-1] - target))
    max_tilt = float(np.max(tilt_arr))
    success = bool(final_error <= position_tolerance and max_tilt <= tilt_limit_deg)

    return {
        "success": success,
        "final_error": final_error,
        "max_tilt_deg": max_tilt,
        "path_length": path_length(ee),
    }


def run_ablation_experiment(
    model_path: Path,
    kin: KukaCupKinematics,
    config: AblationConfig,
    targets: np.ndarray,
    tilt_limit_deg: float,
    position_tolerance: float,
    plan_steps: int,
    sim_substeps: int,
    settle_steps: int,
    run_simulation: bool = True,
) -> List[dict]:
    """Run one ablation variant on a set of targets."""
    planner = AblationPlanner(kin, config, tilt_limit_deg, position_tolerance)
    results = []

    for tid, target in enumerate(targets):
        t0 = time.perf_counter()
        plan = planner.plan_to_target(target, steps=plan_steps)
        plan_time = time.perf_counter() - t0

        row = {
            "target_id": tid,
            "target_x": float(target[0]),
            "target_y": float(target[1]),
            "target_z": float(target[2]),
            "variant": config.name,
            "planned_success": plan["success"],
            "planned_error_m": plan["final_error"],
            "planned_max_tilt_deg": plan["max_tilt_deg"],
            "plan_nfev": plan["nfev_total"],
            "plan_time_s": plan_time,
            "sim_success": False,
            "final_error_m": float("nan"),
            "max_tilt_deg": float("nan"),
            "path_length_m": float("nan"),
        }

        if plan["success"] and run_simulation:
            sim = simulate_plan(
                model_path, plan, tilt_limit_deg, position_tolerance,
                sim_substeps, settle_steps, kin,
            )
            row["sim_success"] = sim["success"]
            row["final_error_m"] = sim["final_error"]
            row["max_tilt_deg"] = sim["max_tilt_deg"]
            row["path_length_m"] = sim["path_length"]

        results.append(row)

    return results


def summarize_results(results: List[dict], variant_name: str) -> dict:
    """Compute summary statistics for a variant's results."""
    total = len(results)
    planned_ok = sum(1 for r in results if r["planned_success"])
    sim_ok = sum(1 for r in results if r["sim_success"] is True)
    sim_planned = sum(1 for r in results if r["planned_success"] is True)

    errors = [
        float(r["final_error_m"])
        for r in results
        if np.isfinite(float(r["final_error_m"]))
    ]
    tilts = [
        float(r["max_tilt_deg"])
        for r in results
        if np.isfinite(float(r["max_tilt_deg"]))
    ]
    plan_times = [r["plan_time_s"] for r in results]
    plan_nfevs = [r["plan_nfev"] for r in results]

    return {
        "variant": variant_name,
        "total_targets": total,
        "ik_reachable": planned_ok,
        "ik_reachability_pct": 100.0 * planned_ok / total,
        "sim_success": sim_ok,
        "sim_success_of_reachable_pct": 100.0 * sim_ok / sim_planned if sim_planned else 0,
        "sim_success_of_total_pct": 100.0 * sim_ok / total,
        "mean_final_error_m": float(np.mean(errors)) if errors else float("nan"),
        "max_final_error_m": float(np.max(errors)) if errors else float("nan"),
        "mean_max_tilt_deg": float(np.mean(tilts)) if tilts else float("nan"),
        "max_max_tilt_deg": float(np.max(tilts)) if tilts else float("nan"),
        "mean_plan_time_s": float(np.mean(plan_times)),
        "mean_plan_nfev": float(np.mean(plan_nfevs)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="kuka_kr20/kuka_kr20_cup_transport.xml")
    parser.add_argument("--targets", type=int, default=100)
    parser.add_argument("--seeds", type=int, default=5, help="Number of random seeds")
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--out", default="outputs/ablation_study")
    parser.add_argument("--tilt-limit-deg", type=float, default=45.0)
    parser.add_argument("--position-tolerance", type=float, default=0.02)
    parser.add_argument("--plan-steps", type=int, default=45)
    parser.add_argument("--sim-substeps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=2000)
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["full_method", "no_tilt_barrier", "position_only", "position_orientation"],
        help="Which ablation variants to run.",
    )
    parser.add_argument("--skip-simulation", action="store_true", help="Only plan, don't run MuJoCo")
    args = parser.parse_args()

    model_path = Path(args.model)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    kin = KukaCupKinematics(model_path)
    all_summaries = []

    for variant_name in args.variants:
        if variant_name not in ABLATION_VARIANTS:
            print(f"Warning: variant '{variant_name}' not found, skipping")
            continue

        config = ABLATION_VARIANTS[variant_name]
        print(f"\n{'='*60}")
        print(f"Variant: {config.name}")
        print(f"  Position: {config.use_position} (w={config.position_weight})")
        print(f"  Orientation: {config.use_orientation} (w={config.orientation_weight})")
        print(f"  Tilt barrier: {config.use_tilt_barrier} (w={config.tilt_barrier_weight})")
        print(f"  Continuity: {config.use_continuity} (w={config.continuity_weight})")
        print(f"  Limit centering: {config.use_limit} (w={config.limit_weight})")
        print(f"  Seeds: {args.seeds}, Targets/seed: {args.targets}")
        print(f"{'='*60}")

        variant_results = []

        for seed_idx in range(args.seeds):
            seed = args.base_seed + seed_idx
            rng = np.random.default_rng(seed)
            targets = sample_targets(rng, args.targets)
            print(f"  Seed {seed} ({seed_idx+1}/{args.seeds}): {len(targets)} targets")

            results = run_ablation_experiment(
                model_path, kin, config, targets,
                args.tilt_limit_deg, args.position_tolerance,
                args.plan_steps, args.sim_substeps, args.settle_steps,
                run_simulation=not args.skip_simulation,
            )
            variant_results.append({"seed": seed, "results": results})

            summary = summarize_results(results, f"{variant_name}_seed{seed}")
            plan_ok = summary["ik_reachable"]
            sim_ok = summary["sim_success"]
            print(f"    IK reachable: {plan_ok}/{args.targets}, Sim success: {sim_ok}/{plan_ok}")

        # Aggregate across seeds
        all_variant_results = []
        for v in variant_results:
            all_variant_results.extend(v["results"])

        aggregate = summarize_results(all_variant_results, variant_name)
        all_summaries.append(aggregate)

        # Save variant results
        variant_out = out_dir / f"{variant_name}_results.csv"
        _write_csv(all_variant_results, variant_out)
        print(f"  Saved {variant_out}")

    # Save summary comparison
    summary_out = out_dir / "ablation_summary.csv"
    _write_csv(all_summaries, summary_out)
    print(f"\nSaved comparison summary to {summary_out}")

    # Print comparison table
    print(f"\n{'='*80}")
    print("COMPARISON TABLE")
    print(f"{'='*80}")
    header = f"{'Variant':<25} {'IK%':>6} {'Sim%':>6} {'MeanErr':>8} {'MaxErr':>8} {'MeanTilt':>8} {'MaxTilt':>8} {'Time(s)':>8}"
    print(header)
    print("-" * 80)
    for s in all_summaries:
        print(
            f"{s['variant']:<25} "
            f"{s['ik_reachability_pct']:5.1f}% "
            f"{s['sim_success_of_total_pct']:5.1f}% "
            f"{s['mean_final_error_m']*1000:7.1f}mm "
            f"{s['max_final_error_m']*1000:7.1f}mm "
            f"{s['mean_max_tilt_deg']:7.2f}° "
            f"{s['max_max_tilt_deg']:7.2f}° "
            f"{s['mean_plan_time_s']:7.3f}s"
        )


def _write_csv(rows: list, path: Path) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

# 推荐调用：
# python src/baseline_comparison.py --tilt-limit-deg 10 \
#   --seeds 3 --targets 50 \
#   --variants full_tight10 no_barrier_tight10 \
#   --out outputs/ablation_study_tight10
