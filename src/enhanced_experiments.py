"""
Enhanced experiment suite for Round 2: multi-seed, sensitivity, expanded workspace, dynamic metrics.
Extends baseline_comparison.py with comprehensive evaluation.
"""
from __future__ import annotations

import argparse, csv, json, time, sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mujoco
import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kinematics import KukaCupKinematics, WORLD_Z, smoothstep, RobotState
from planner import path_length
from baseline_comparison import (
    AblationConfig, AblationPlanner, ABLATION_VARIANTS,
    sample_targets as _sample_targets, simulate_plan as _simulate_plan,
)


# ============================================================================
# 1. Expanded target sampling (wider workspace + challenging regions)
# ============================================================================

def sample_targets_expanded(rng: np.random.Generator, count: int) -> Tuple[np.ndarray, List[str]]:
    """Sample targets across a wider workspace including challenging regions."""
    targets = []
    regions = []
    attempts = 0
    max_attempts = max(500, count * 120)

    # Region definitions
    region_configs = [
        ("standard", 0.55, 1.35, -0.78, 0.78, 0.70, 1.70, 0.35),  # standard front
        ("wide_azimuth", 0.55, 1.20, -1.20, 1.20, 0.70, 1.70, 0.20),  # wider azimuth
        ("low_reach", 0.55, 1.20, -0.60, 0.60, 0.40, 0.75, 0.15),  # near ground
        ("high_reach", 0.55, 1.20, -0.50, 0.50, 1.65, 1.90, 0.15),  # high reach
        ("far_reach", 1.15, 1.50, -0.50, 0.50, 0.80, 1.50, 0.15),  # near max reach
    ]

    per_region = count // len(region_configs)
    extra = count - per_region * len(region_configs)

    for idx, (region, r_min, r_max, th_min, th_max, h_min, h_max, _) in enumerate(region_configs):
        n = per_region + (1 if idx < extra else 0)
        region_targets = 0
        while region_targets < n and attempts < max_attempts:
            attempts += 1
            radius = rng.uniform(r_min, r_max)
            theta = rng.uniform(th_min, th_max)
            height = rng.uniform(h_min, h_max)
            x = radius * np.cos(theta)
            y = radius * np.sin(theta)
            if x < 0.15:
                continue
            targets.append([x, y, z := height])
            regions.append(region)
            region_targets += 1

    return np.asarray(targets, dtype=float), regions


# ============================================================================
# 2. Weight sensitivity analysis
# ============================================================================

SENSITIVITY_GRID = {
    "position_weight": [3.0, 7.5, 15.0, 30.0],
    "orientation_weight": [0.10, 0.45, 0.90, 1.80, 3.60],
    "tilt_barrier_weight": [5.0, 10.0, 18.0, 36.0, 72.0],
    "continuity_weight": [0.01, 0.04, 0.08, 0.16, 0.32],
    "limit_weight": [0.005, 0.0125, 0.025, 0.05, 0.10],
}


# ============================================================================
# 3. Dynamic spill proxy metrics
# ============================================================================

def compute_dynamic_metrics(
    ee_pos: np.ndarray, tilt_deg: np.ndarray, time_arr: np.ndarray, cup_axis: np.ndarray = None
) -> dict:
    """Compute acceleration, jerk, and angular velocity proxies for spill risk."""
    if len(ee_pos) < 3 or len(time_arr) < 3:
        return {"max_accel": 0.0, "max_jerk": 0.0, "max_ang_vel": 0.0, "avg_accel": 0.0}

    dt = np.diff(time_arr)
    if np.any(dt <= 0):
        return {"max_accel": float("nan"), "max_jerk": float("nan"), "max_ang_vel": float("nan"), "avg_accel": float("nan")}

    # Cartesian velocities
    vel = np.diff(ee_pos, axis=0) / dt[:, np.newaxis]
    speed = np.linalg.norm(vel, axis=1)

    # Cartesian accelerations
    accel = np.diff(vel, axis=0) / dt[1:, np.newaxis]
    accel_mag = np.linalg.norm(accel, axis=1)

    # Jerk
    jerk = np.diff(accel, axis=0) / dt[2:, np.newaxis]
    jerk_mag = np.linalg.norm(jerk, axis=1)

    # Angular velocity (from tilt time series)
    tilt_rad = np.radians(tilt_deg)
    ang_vel = np.abs(np.diff(tilt_rad) / dt)

    return {
        "max_accel": float(np.max(accel_mag)) if len(accel_mag) > 0 else 0.0,
        "max_jerk": float(np.max(jerk_mag)) if len(jerk_mag) > 0 else 0.0,
        "max_ang_vel": float(np.max(ang_vel)) if len(ang_vel) > 0 else 0.0,
        "avg_accel": float(np.mean(accel_mag)) if len(accel_mag) > 0 else 0.0,
        "avg_ang_vel": float(np.mean(ang_vel)) if len(ang_vel) > 0 else 0.0,
    }


# ============================================================================
# 4. Convergence analysis
# ============================================================================

def analyze_convergence(planned_qpos: np.ndarray, kin: KukaCupKinematics) -> dict:
    """Analyze convergence properties of a planned trajectory."""
    if len(planned_qpos) < 2:
        return {}

    joint_disp = np.diff(planned_qpos, axis=0)
    joint_vel = np.linalg.norm(joint_disp, axis=1)

    return {
        "max_joint_displacement": float(np.max(joint_vel)),
        "mean_joint_displacement": float(np.mean(joint_vel)),
        "total_joint_travel": float(np.sum(joint_vel)),
        "path_smoothness": float(np.std(joint_vel)),
    }


# ============================================================================
# 5. Full enhanced experiment runner
# ============================================================================

def run_sensitivity_experiment(
    model_path: Path, kin: KukaCupKinematics,
    targets: np.ndarray,
    param_name: str, param_values: List[float],
    base_config: AblationConfig,
    tilt_limit_deg: float, position_tolerance: float,
    plan_steps: int, out_dir: Path,
) -> List[dict]:
    """Sweep one parameter across multiple values."""
    results = []

    for value in param_values:
        config = AblationConfig(
            name=f"{param_name}={value}",
            **{param_name: value},
        )
        # Copy all other params from base
        for field_name in ["use_position", "use_orientation", "use_tilt_barrier", "use_continuity", "use_limit"]:
            setattr(config, field_name, getattr(base_config, field_name))
        for other_param in ["position_weight", "orientation_weight", "tilt_barrier_weight", "continuity_weight", "limit_weight"]:
            if other_param != param_name:
                setattr(config, other_param, getattr(base_config, other_param))

        planner = AblationPlanner(kin, config, tilt_limit_deg, position_tolerance)

        for tid, target in enumerate(targets):
            plan = planner.plan_to_target(target, steps=plan_steps)
            results.append({
                "param": param_name,
                "value": value,
                "target_id": tid,
                "planned_success": plan["success"],
                "planned_error_m": plan["final_error"],
                "planned_max_tilt_deg": plan["max_tilt_deg"],
                "plan_nfev": plan["nfev_total"],
            })

    return results


def run_single_target_full_analysis(
    model_path: Path, kin: KukaCupKinematics,
    target: np.ndarray, config: AblationConfig,
    tilt_limit_deg: float, position_tolerance: float,
    plan_steps: int, sim_substeps: int, settle_steps: int,
) -> dict:
    """Run full analysis for one target: plan + sim + dynamic metrics + convergence."""
    planner = AblationPlanner(kin, config, tilt_limit_deg, position_tolerance)
    plan = planner.plan_to_target(target, steps=plan_steps)

    result = {
        "target_x": float(target[0]),
        "target_y": float(target[1]),
        "target_z": float(target[2]),
        "planned_success": plan["success"],
        "planned_error_m": plan["final_error"],
        "planned_max_tilt_deg": plan["max_tilt_deg"],
        "plan_nfev": plan["nfev_total"],
    }

    if plan["success"]:
        # Convergence analysis
        conv = analyze_convergence(np.asarray(plan["qpos"], dtype=float), kin)
        result.update({f"conv_{k}": v for k, v in conv.items()})

        # Simulation
        sim = _simulate_plan(model_path, plan, tilt_limit_deg, position_tolerance, sim_substeps, settle_steps, kin)
        result.update({
            "sim_success": sim["success"],
            "sim_final_error_m": sim["final_error"],
            "sim_max_tilt_deg": sim["max_tilt_deg"],
            "sim_path_length_m": sim["path_length"],
        })

        # Dynamic metrics
        if "ee_pos" in plan:
            ee = np.asarray(plan["ee_pos"], dtype=float)
            tilt_arr = np.asarray(plan["tilt_deg"], dtype=float)
            # Synthetic time
            t_arr = np.linspace(0, 2.0, len(ee))
            dyn = compute_dynamic_metrics(ee, tilt_arr, t_arr)
            result.update({f"dyn_{k}": v for k, v in dyn.items()})
    else:
        result.update({
            "sim_success": False,
            "sim_final_error_m": float("nan"),
            "sim_max_tilt_deg": float("nan"),
            "sim_path_length_m": float("nan"),
        })

    return result


def main():
    parser = argparse.ArgumentParser(description="Enhanced experiment suite for Round 2 review")
    parser.add_argument("--model", default="kuka_kr20/kuka_kr20_cup_transport.xml")
    parser.add_argument("--targets", type=int, default=100)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--out", default="outputs/round2_experiments")
    parser.add_argument("--tilt-limit-deg", type=float, default=45.0)
    parser.add_argument("--position-tolerance", type=float, default=0.02)
    parser.add_argument("--plan-steps", type=int, default=45)
    parser.add_argument("--sim-substeps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=2000)
    parser.add_argument("--mode", choices=["all", "multiseed", "sensitivity", "expanded", "dynamic", "full"], default="all")
    parser.add_argument("--skip-simulation", action="store_true")
    args = parser.parse_args()

    model_path = Path(args.model)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    kin = KukaCupKinematics(model_path)
    base_config = ABLATION_VARIANTS["full_method"]
    run_sim = not args.skip_simulation

    all_mode_summaries = {}

    # ---- Multi-seed evaluation ----
    if args.mode in ("all", "multiseed", "full"):
        print("\n" + "="*70)
        print("MULTI-SEED EVALUATION (10 seeds)")
        print("="*70)

        multi_seed_results = []
        for seed_idx in range(args.seeds):
            seed = args.base_seed + seed_idx
            rng = np.random.default_rng(seed)
            targets = _sample_targets(rng, args.targets)
            planner = AblationPlanner(kin, base_config, args.tilt_limit_deg, args.position_tolerance)

            seed_ok_plan = 0
            seed_ok_sim = 0
            seed_results = []

            for tid, target in enumerate(targets):
                plan = planner.plan_to_target(target, steps=args.plan_steps)
                row = {
                    "seed": seed, "target_id": tid,
                    "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
                    "planned_success": plan["success"],
                    "planned_error_m": plan["final_error"],
                    "planned_max_tilt_deg": plan["max_tilt_deg"],
                    "plan_nfev": plan["nfev_total"],
                    "sim_success": False,
                    "final_error_m": float("nan"),
                    "max_tilt_deg": float("nan"),
                    "path_length_m": float("nan"),
                }
                if plan["success"]:
                    seed_ok_plan += 1
                    if run_sim:
                        sim = _simulate_plan(model_path, plan, args.tilt_limit_deg, args.position_tolerance,
                                            args.sim_substeps, args.settle_steps, kin)
                        row["sim_success"] = sim["success"]
                        row["final_error_m"] = sim["final_error"]
                        row["max_tilt_deg"] = sim["max_tilt_deg"]
                        row["path_length_m"] = sim["path_length"]
                        if sim["success"]:
                            seed_ok_sim += 1
                seed_results.append(row)

            multi_seed_results.extend(seed_results)
            print(f"  Seed {seed}: Plan OK={seed_ok_plan}/{args.targets}, Sim OK={seed_ok_sim}/{seed_ok_plan}")

        # Compute multi-seed statistics
        all_sim_ok = [r for r in multi_seed_results if r["sim_success"] is True]
        all_sim_rates = []
        for seed_idx in range(args.seeds):
            seed = args.base_seed + seed_idx
            seed_rows = [r for r in multi_seed_results if r["seed"] == seed]
            plan_ok = sum(1 for r in seed_rows if r["planned_success"])
            sim_ok = sum(1 for r in seed_rows if r["sim_success"] is True)
            all_sim_rates.append(sim_ok / plan_ok * 100 if plan_ok else 0)

        errors = [r["final_error_m"] for r in all_sim_ok]
        tilts = [r["max_tilt_deg"] for r in all_sim_ok]

        all_mode_summaries["multi_seed"] = {
            "total_targets": len(multi_seed_results),
            "mean_sim_rate_pct": float(np.mean(all_sim_rates)),
            "std_sim_rate_pct": float(np.std(all_sim_rates)),
            "min_sim_rate_pct": float(np.min(all_sim_rates)),
            "max_sim_rate_pct": float(np.max(all_sim_rates)),
            "mean_error_mm": float(np.mean(errors)*1000) if errors else float("nan"),
            "std_error_mm": float(np.std(errors)*1000) if errors else float("nan"),
            "mean_tilt_deg": float(np.mean(tilts)) if tilts else float("nan"),
            "std_tilt_deg": float(np.std(tilts)) if tilts else float("nan"),
        }

        # Save
        _write_csv(multi_seed_results, out_dir / "multiseed_results.csv")
        _write_csv([all_mode_summaries["multi_seed"]], out_dir / "multiseed_summary.csv")

        print(f"\n  Multi-seed summary: "
              f"rate={all_mode_summaries['multi_seed']['mean_sim_rate_pct']:.1f}% "
              f"±{all_mode_summaries['multi_seed']['std_sim_rate_pct']:.1f}%, "
              f"error={all_mode_summaries['multi_seed']['mean_error_mm']:.1f}±{all_mode_summaries['multi_seed']['std_error_mm']:.1f}mm, "
              f"tilt={all_mode_summaries['multi_seed']['mean_tilt_deg']:.1f}±{all_mode_summaries['multi_seed']['std_tilt_deg']:.1f}deg")

    # ---- Sensitivity analysis ----
    if args.mode in ("all", "sensitivity", "full"):
        print("\n" + "="*70)
        print("WEIGHT SENSITIVITY ANALYSIS")
        print("="*70)

        rng = np.random.default_rng(99)
        sens_targets = _sample_targets(rng, min(50, args.targets))
        sens_summaries = []

        for param_name, values in SENSITIVITY_GRID.items():
            print(f"\n  Parameter: {param_name}")
            for value in values:
                config = AblationConfig(name=f"{param_name}={value}")
                for fname in ["use_position", "use_orientation", "use_tilt_barrier", "use_continuity", "use_limit"]:
                    setattr(config, fname, getattr(base_config, fname))
                for other in ["position_weight", "orientation_weight", "tilt_barrier_weight", "continuity_weight", "limit_weight"]:
                    if other != param_name:
                        setattr(config, other, getattr(base_config, other))
                setattr(config, param_name, value)

                planner = AblationPlanner(kin, config, args.tilt_limit_deg, args.position_tolerance)
                plan_ok = 0
                for target in sens_targets:
                    plan = planner.plan_to_target(target, steps=args.plan_steps)
                    if plan["success"]:
                        plan_ok += 1

                rate = 100.0 * plan_ok / len(sens_targets)
                print(f"    {param_name}={value:.4f}: IK rate={rate:.1f}%")
                sens_summaries.append({"param": param_name, "value": value, "ik_rate_pct": rate})

        _write_csv(sens_summaries, out_dir / "sensitivity_results.csv")
        all_mode_summaries["sensitivity"] = sens_summaries

    # ---- Expanded workspace ----
    if args.mode in ("all", "expanded", "full"):
        print("\n" + "="*70)
        print("EXPANDED WORKSPACE ANALYSIS")
        print("="*70)

        rng = np.random.default_rng(77)
        expanded_targets, regions = sample_targets_expanded(rng, args.targets)
        planner = AblationPlanner(kin, base_config, args.tilt_limit_deg, args.position_tolerance)

        expanded_results = []
        region_stats = defaultdict(lambda: {"plan_ok": 0, "sim_ok": 0, "total": 0})

        for tid, (target, region) in enumerate(zip(expanded_targets, regions)):
            plan = planner.plan_to_target(target, steps=args.plan_steps)
            row = {
                "target_id": tid, "region": region,
                "target_x": float(target[0]), "target_y": float(target[1]), "target_z": float(target[2]),
                "planned_success": plan["success"],
                "planned_error_m": plan["final_error"],
                "planned_max_tilt_deg": plan["max_tilt_deg"],
                "plan_nfev": plan["nfev_total"],
                "sim_success": False, "final_error_m": float("nan"), "max_tilt_deg": float("nan"),
            }
            region_stats[region]["total"] += 1
            if plan["success"]:
                region_stats[region]["plan_ok"] += 1
                if run_sim:
                    sim = _simulate_plan(model_path, plan, args.tilt_limit_deg, args.position_tolerance,
                                        args.sim_substeps, args.settle_steps, kin)
                    row["sim_success"] = sim["success"]
                    row["final_error_m"] = sim["final_error"]
                    row["max_tilt_deg"] = sim["max_tilt_deg"]
                    if sim["success"]:
                        region_stats[region]["sim_ok"] += 1
            expanded_results.append(row)

        _write_csv(expanded_results, out_dir / "expanded_workspace_results.csv")

        region_summary = []
        for region, stats in sorted(region_stats.items()):
            plan_rate = 100.0 * stats["plan_ok"] / stats["total"] if stats["total"] else 0
            sim_rate = 100.0 * stats["sim_ok"] / stats["total"] if stats["total"] else 0
            print(f"  {region}: Plan={stats['plan_ok']}/{stats['total']} ({plan_rate:.1f}%), Sim={stats['sim_ok']}/{stats['total']} ({sim_rate:.1f}%)")
            region_summary.append({"region": region, "total": stats["total"],
                                   "plan_ok": stats["plan_ok"], "sim_ok": stats["sim_ok"],
                                   "plan_rate_pct": plan_rate, "sim_rate_pct": sim_rate})

        _write_csv(region_summary, out_dir / "expanded_workspace_summary.csv")
        all_mode_summaries["expanded"] = region_summary

    # ---- Dynamic metrics + full analysis (subset) ----
    if args.mode in ("all", "dynamic", "full"):
        print("\n" + "="*70)
        print("DYNAMIC METRICS + CONVERGENCE ANALYSIS")
        print("="*70)

        rng = np.random.default_rng(55)
        dyn_targets = _sample_targets(rng, min(30, args.targets))
        dyn_results = []

        for tid, target in enumerate(dyn_targets):
            result = run_single_target_full_analysis(
                model_path, kin, target, base_config,
                args.tilt_limit_deg, args.position_tolerance,
                args.plan_steps, args.sim_substeps, args.settle_steps,
            )
            result["target_id"] = tid
            dyn_results.append(result)
            status = "OK" if result.get("sim_success") else "FAIL"
            print(f"  Target {tid}: {status} | err={result.get('sim_final_error_m', float('nan'))*1000:.1f}mm | "
                  f"accel={result.get('dyn_max_accel', 0):.1f}m/s² | "
                  f"jerk={result.get('dyn_max_jerk', 0):.1f}m/s³")

        _write_csv(dyn_results, out_dir / "dynamic_metrics_results.csv")
        all_mode_summaries["dynamic"] = dyn_results

    # Save all summaries
    with (out_dir / "round2_summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_mode_summaries, f, indent=2, default=str, ensure_ascii=False)

    print(f"\n{'='*70}")
    print("ROUND 2 EXPERIMENTS COMPLETE")
    print(f"Results saved to: {out_dir}")
    print(f"{'='*70}")


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
