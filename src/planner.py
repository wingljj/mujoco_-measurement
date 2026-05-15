"""Constrained inverse-kinematics planner for cup-safe KR20 motion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np
from scipy.optimize import least_squares

try:
    from .kinematics import KukaCupKinematics, RobotState, WORLD_Z, smoothstep
except ImportError:  # pragma: no cover - supports direct script execution
    from kinematics import KukaCupKinematics, RobotState, WORLD_Z, smoothstep


@dataclass(frozen=True)
class IKResult:
    success: bool
    qpos: np.ndarray
    ee_pos: np.ndarray
    tilt_deg: float
    position_error: float
    cost: float
    message: str


@dataclass(frozen=True)
class TrajectoryPlan:
    success: bool
    qpos: np.ndarray
    ee_pos: np.ndarray
    tilt_deg: np.ndarray
    target: np.ndarray
    final_error: float
    max_tilt_deg: float
    message: str


class CupSafePlanner:
    """IK and path planner that keeps the cup axis close to world vertical."""

    def __init__(
        self,
        kin: KukaCupKinematics,
        tilt_limit_deg: float = 45.0,
        position_tolerance: float = 0.02,
        tilt_weight: float = 0.90,
        continuity_weight: float = 0.08,
        limit_weight: float = 0.025,
    ) -> None:
        self.kin = kin
        self.tilt_limit_deg = float(tilt_limit_deg)
        self.position_tolerance = float(position_tolerance)
        self.tilt_weight = float(tilt_weight)
        self.continuity_weight = float(continuity_weight)
        self.limit_weight = float(limit_weight)
        self._tilt_limit_rad = np.radians(self.tilt_limit_deg)

    def solve_ik(
        self,
        target: Iterable[float],
        seed_qpos: Iterable[float] | None = None,
        max_nfev: int = 120,
    ) -> IKResult:
        target_array = np.asarray(target, dtype=float)
        if seed_qpos is None:
            seed = self.kin.default_qpos()
        else:
            seed = self.kin.clip(np.asarray(seed_qpos, dtype=float))

        def residual(qpos: np.ndarray) -> np.ndarray:
            state = self.kin.state(qpos)
            position_residual = 7.5 * (state.ee_pos - target_array)
            vertical_residual = self.tilt_weight * np.cross(state.cup_axis, WORLD_Z)
            continuity_residual = self.continuity_weight * (qpos - seed)
            limit_residual = self.limit_weight * self.kin.normalized_limit_distance(qpos)

            tilt_rad = np.radians(state.tilt_deg)
            excess = max(0.0, tilt_rad - self._tilt_limit_rad)
            tilt_barrier = np.array([18.0 * excess], dtype=float)

            return np.concatenate(
                [
                    position_residual,
                    vertical_residual,
                    continuity_residual,
                    limit_residual,
                    tilt_barrier,
                ]
            )

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
        position_error = float(np.linalg.norm(state.ee_pos - target_array))
        success = bool(
            result.success
            and position_error <= self.position_tolerance
            and state.tilt_deg <= self.tilt_limit_deg
        )
        message = result.message if isinstance(result.message, str) else str(result.message)
        return IKResult(
            success=success,
            qpos=self.kin.clip(result.x),
            ee_pos=state.ee_pos,
            tilt_deg=state.tilt_deg,
            position_error=position_error,
            cost=float(result.cost),
            message=message,
        )

    def plan_to_target(
        self,
        target: Iterable[float],
        start_qpos: Iterable[float] | None = None,
        steps: int = 45,
    ) -> TrajectoryPlan:
        if start_qpos is None:
            start_state = self.kin.state(self.kin.default_qpos())
        else:
            start_state = self.kin.state(start_qpos)

        target_array = np.asarray(target, dtype=float)
        t_values = smoothstep(np.linspace(0.0, 1.0, int(steps)))
        qpos_path: List[np.ndarray] = []
        ee_path: List[np.ndarray] = []
        tilt_path: List[float] = []
        seed = start_state.qpos.copy()
        messages: List[str] = []

        for alpha in t_values:
            waypoint = (1.0 - alpha) * start_state.ee_pos + alpha * target_array
            ik = self.solve_ik(waypoint, seed_qpos=seed)
            qpos_path.append(ik.qpos)
            ee_path.append(ik.ee_pos)
            tilt_path.append(ik.tilt_deg)
            seed = ik.qpos
            if not ik.success:
                messages.append(
                    f"waypoint failed: err={ik.position_error:.4f} m, "
                    f"tilt={ik.tilt_deg:.2f} deg"
                )
                break

        qpos = np.asarray(qpos_path, dtype=float)
        ee_pos = np.asarray(ee_path, dtype=float)
        tilt_deg = np.asarray(tilt_path, dtype=float)
        final_error = (
            float(np.linalg.norm(ee_pos[-1] - target_array)) if len(ee_pos) else float("inf")
        )
        max_tilt = float(np.max(tilt_deg)) if len(tilt_deg) else float("inf")
        success = bool(
            len(qpos_path) == len(t_values)
            and final_error <= self.position_tolerance
            and max_tilt <= self.tilt_limit_deg
        )
        message = "ok" if success else "; ".join(messages[-2:]) or "trajectory failed"
        return TrajectoryPlan(
            success=success,
            qpos=qpos,
            ee_pos=ee_pos,
            tilt_deg=tilt_deg,
            target=target_array,
            final_error=final_error,
            max_tilt_deg=max_tilt,
            message=message,
        )


def path_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))
