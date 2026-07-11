"""Task-priority IK baseline for the KR20 cup-transport benchmark."""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent))
from baseline_comparison import sample_targets, simulate_plan
from kinematics import KukaCupKinematics, WORLD_Z, smoothstep


def finite_difference_jacobian(
    function: Callable[[np.ndarray], np.ndarray],
    qpos: np.ndarray,
    step: float = 5e-5,
) -> np.ndarray:
    """Return a forward finite-difference Jacobian."""
    qpos = np.asarray(qpos, dtype=float)
    base = np.asarray(function(qpos), dtype=float)
    jacobian = np.empty((base.size, qpos.size), dtype=float)
    for joint_index in range(qpos.size):
        shifted = qpos.copy()
        shifted[joint_index] += step
        jacobian[:, joint_index] = (
            np.asarray(function(shifted), dtype=float) - base
        ) / step
    return jacobian


class PriorityIKPlanner:
    """Position-first IK with upright orientation projected into its null space."""

    def __init__(
        self,
        kin: KukaCupKinematics,
        position_tolerance: float = 0.02,
        tilt_limit_deg: float = 45.0,
        damping: float = 1e-3,
        finite_difference_step: float = 5e-5,
        max_iterations: int = 60,
    ) -> None:
        self.kin = kin
        self.position_tolerance = float(position_tolerance)
        self.tilt_limit_deg = float(tilt_limit_deg)
        self.damping = float(damping)
        self.finite_difference_step = float(finite_difference_step)
        self.max_iterations = int(max_iterations)

    def solve_waypoint(
        self,
        target: Iterable[float],
        seed_qpos: Iterable[float],
    ) -> dict:
        target = np.asarray(target, dtype=float)
        qpos = self.kin.clip(np.asarray(seed_qpos, dtype=float))
        iterations = 0

        for iterations in range(1, self.max_iterations + 1):
            state = self.kin.state(qpos)
            position_error = target - state.ee_pos
            orientation_residual = np.cross(state.cup_axis, WORLD_Z)
            if (
                np.linalg.norm(position_error) <= self.position_tolerance
                and state.tilt_deg <= self.tilt_limit_deg
            ):
                break

            position_jacobian = finite_difference_jacobian(
                lambda q: self.kin.state(q).ee_pos,
                qpos,
                self.finite_difference_step,
            )
            orientation_jacobian = finite_difference_jacobian(
                lambda q: np.cross(self.kin.state(q).cup_axis, WORLD_Z),
                qpos,
                self.finite_difference_step,
            )

            position_pinv = np.linalg.pinv(
                position_jacobian, rcond=self.damping
            )
            orientation_pinv = np.linalg.pinv(
                orientation_jacobian, rcond=self.damping
            )
            null_projector = (
                np.eye(self.kin.nq_robot) - position_pinv @ position_jacobian
            )
            q_delta = (
                position_pinv @ position_error
                - null_projector @ orientation_pinv @ orientation_residual
            )
            delta_norm = float(np.linalg.norm(q_delta))
            if delta_norm > 0.20:
                q_delta *= 0.20 / delta_norm
            qpos = self.kin.clip(qpos + 0.7 * q_delta)

        state = self.kin.state(qpos)
        final_error = float(np.linalg.norm(state.ee_pos - target))
        success = bool(
            final_error <= self.position_tolerance
            and state.tilt_deg <= self.tilt_limit_deg
        )
        return {
            "success": success,
            "qpos": qpos,
            "ee_pos": state.ee_pos,
            "tilt_deg": state.tilt_deg,
            "position_error": final_error,
            "iterations": iterations,
        }

    def plan_to_target(
        self,
        target: Iterable[float],
        start_qpos: Iterable[float] | None = None,
        steps: int = 45,
    ) -> dict:
        if start_qpos is None:
            start_qpos = self.kin.default_qpos()
        start_state = self.kin.state(start_qpos)
        target = np.asarray(target, dtype=float)
        alphas = smoothstep(np.linspace(0.0, 1.0, int(steps)))

        qpos_path = []
        ee_path = []
        tilt_path = []
        seed = np.asarray(start_qpos, dtype=float)
        iteration_total = 0
        message = "ok"

        for alpha in alphas:
            waypoint = (1.0 - alpha) * start_state.ee_pos + alpha * target
            result = self.solve_waypoint(waypoint, seed)
            qpos_path.append(result["qpos"])
            ee_path.append(result["ee_pos"])
            tilt_path.append(result["tilt_deg"])
            iteration_total += result["iterations"]
            seed = result["qpos"]
            if not result["success"]:
                message = (
                    f"waypoint failed: err={result['position_error']:.4f}m, "
                    f"tilt={result['tilt_deg']:.2f}deg"
                )
                break

        qpos = np.asarray(qpos_path, dtype=float)
        ee_pos = np.asarray(ee_path, dtype=float)
        tilt_deg = np.asarray(tilt_path, dtype=float)
        final_error = (
            float(np.linalg.norm(ee_pos[-1] - target))
            if len(ee_pos)
            else float("inf")
        )
        max_tilt = float(np.max(tilt_deg)) if len(tilt_deg) else float("inf")
        success = bool(
            len(qpos_path) == len(alphas)
            and final_error <= self.position_tolerance
            and max_tilt <= self.tilt_limit_deg
        )
        return {
            "success": success,
            "qpos": qpos,
            "ee_pos": ee_pos,
            "tilt_deg": tilt_deg,
            "target": target,
            "final_error": final_error,
            "max_tilt_deg": max_tilt,
            "nfev_total": iteration_total,
            "message": message if not success else "ok",
        }


def summarize_results(results: list[dict]) -> dict:
    """Summarize priority-IK rows using the ablation-summary schema."""
    total = len(results)
    planned = sum(bool(row["planned_success"]) for row in results)
    simulated = sum(row["sim_success"] is True for row in results)
    errors = [row["final_error_m"] for row in results if row["sim_success"] is True]
    tilts = [row["max_tilt_deg"] for row in results if row["sim_success"] is True]
    plan_times = [row["plan_time_s"] for row in results]
    nfevs = [row["plan_nfev"] for row in results]
    return {
        "variant": "priority_ik",
        "total_targets": total,
        "ik_reachable": planned,
        "ik_reachability_pct": 100.0 * planned / total if total else 0.0,
        "sim_success": simulated,
        "sim_success_of_reachable_pct": (
            100.0 * simulated / planned if planned else 0.0
        ),
        "sim_success_of_total_pct": 100.0 * simulated / total if total else 0.0,
        "mean_final_error_m": float(np.mean(errors)) if errors else float("nan"),
        "max_final_error_m": float(np.max(errors)) if errors else float("nan"),
        "mean_max_tilt_deg": float(np.mean(tilts)) if tilts else float("nan"),
        "max_max_tilt_deg": float(np.max(tilts)) if tilts else float("nan"),
        "mean_plan_time_s": float(np.mean(plan_times)) if plan_times else float("nan"),
        "mean_plan_nfev": float(np.mean(nfevs)) if nfevs else float("nan"),
    }


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default="kuka_kr20/kuka_kr20_cup_transport.xml"
    )
    parser.add_argument("--targets", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--out", default="outputs/external_baselines")
    parser.add_argument("--tilt-limit-deg", type=float, default=45.0)
    parser.add_argument("--position-tolerance", type=float, default=0.02)
    parser.add_argument("--plan-steps", type=int, default=45)
    parser.add_argument("--sim-substeps", type=int, default=30)
    parser.add_argument("--settle-steps", type=int, default=2000)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    model_path = Path(args.model)
    out_dir = Path(args.out)
    kin = KukaCupKinematics(model_path)
    planner = PriorityIKPlanner(
        kin,
        position_tolerance=args.position_tolerance,
        tilt_limit_deg=args.tilt_limit_deg,
    )
    rows = []

    for seed_index in range(args.seeds):
        seed = args.base_seed + seed_index
        targets = sample_targets(np.random.default_rng(seed), args.targets)
        for target_id, target in enumerate(targets):
            start_time = time.perf_counter()
            plan = planner.plan_to_target(target, steps=args.plan_steps)
            plan_time = time.perf_counter() - start_time
            row = {
                "target_id": target_id,
                "target_x": float(target[0]),
                "target_y": float(target[1]),
                "target_z": float(target[2]),
                "variant": "priority_ik",
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
            if plan["success"]:
                simulation = simulate_plan(
                    model_path,
                    plan,
                    args.tilt_limit_deg,
                    args.position_tolerance,
                    args.sim_substeps,
                    args.settle_steps,
                    kin,
                )
                row.update(
                    {
                        "sim_success": simulation["success"],
                        "final_error_m": simulation["final_error"],
                        "max_tilt_deg": simulation["max_tilt_deg"],
                        "path_length_m": simulation["path_length"],
                    }
                )
            rows.append(row)
        seed_rows = rows[-args.targets :]
        print(
            f"Seed {seed}: IK={sum(r['planned_success'] for r in seed_rows)}/"
            f"{args.targets}, Sim={sum(r['sim_success'] is True for r in seed_rows)}/"
            f"{args.targets}"
        )

    write_csv(rows, out_dir / "priority_ik_results.csv")
    summary = summarize_results(rows)
    write_csv([summary], out_dir / "priority_ik_summary.csv")
    print(f"Saved results to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
