"""Kinematics helpers for the KUKA KR20 cup transport experiment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import mujoco
import numpy as np


WORLD_Z = np.array([0.0, 0.0, 1.0], dtype=float)


@dataclass(frozen=True)
class RobotState:
    """Compact task-space state used by the planner and logger."""

    qpos: np.ndarray
    ee_pos: np.ndarray
    cup_axis: np.ndarray
    tilt_deg: float


class KukaCupKinematics:
    """MuJoCo-backed forward kinematics and task metrics."""

    def __init__(
        self,
        model_path: str | Path,
        ee_site: str = "ee_site",
        cup_axis_base_site: str = "cup_axis_base_site",
        cup_axis_tip_site: str = "cup_axis_tip_site",
    ) -> None:
        self.model_path = Path(model_path)
        self.model = mujoco.MjModel.from_xml_path(str(self.model_path))
        self.data = mujoco.MjData(self.model)

        self.ee_site_id = self._site_id(ee_site)
        self.axis_base_site_id = self._site_id(cup_axis_base_site)
        self.axis_tip_site_id = self._site_id(cup_axis_tip_site)

        self.joint_names = [f"joint_{idx}" for idx in range(1, 7)]
        self.joint_ids = np.array(
            [self._joint_id(name) for name in self.joint_names], dtype=int
        )
        self.qpos_addr = np.array(
            [self.model.jnt_qposadr[joint_id] for joint_id in self.joint_ids],
            dtype=int,
        )
        self.dof_addr = np.array(
            [self.model.jnt_dofadr[joint_id] for joint_id in self.joint_ids],
            dtype=int,
        )
        self.lower = self.model.jnt_range[self.joint_ids, 0].copy()
        self.upper = self.model.jnt_range[self.joint_ids, 1].copy()
        self.center = 0.5 * (self.lower + self.upper)
        self.span = self.upper - self.lower

    def _site_id(self, name: str) -> int:
        site_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)
        if site_id < 0:
            raise ValueError(f"Site '{name}' was not found in {self.model_path}")
        return site_id

    def _joint_id(self, name: str) -> int:
        joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise ValueError(f"Joint '{name}' was not found in {self.model_path}")
        return joint_id

    @property
    def nq_robot(self) -> int:
        return len(self.qpos_addr)

    def default_qpos(self) -> np.ndarray:
        return self.model.qpos0[self.qpos_addr].copy()

    def clip(self, qpos: np.ndarray, margin: float = 1e-5) -> np.ndarray:
        return np.clip(np.asarray(qpos, dtype=float), self.lower + margin, self.upper - margin)

    def set_qpos(self, qpos: Iterable[float]) -> None:
        qpos_array = self.clip(np.asarray(qpos, dtype=float), margin=0.0)
        self.data.qpos[self.qpos_addr] = qpos_array
        self.data.qvel[:] = 0.0
        self.data.ctrl[:] = qpos_array[: self.model.nu]
        mujoco.mj_forward(self.model, self.data)

    def state(self, qpos: Iterable[float] | None = None) -> RobotState:
        if qpos is not None:
            self.set_qpos(qpos)
        else:
            mujoco.mj_forward(self.model, self.data)

        ee_pos = self.data.site_xpos[self.ee_site_id].copy()
        cup_axis = self.cup_axis()
        tilt_deg = self.tilt_angle_deg(cup_axis)
        return RobotState(
            qpos=self.data.qpos[self.qpos_addr].copy(),
            ee_pos=ee_pos,
            cup_axis=cup_axis,
            tilt_deg=tilt_deg,
        )

    def ee_position(self, qpos: Iterable[float] | None = None) -> np.ndarray:
        return self.state(qpos).ee_pos

    def cup_axis(self) -> np.ndarray:
        base = self.data.site_xpos[self.axis_base_site_id]
        tip = self.data.site_xpos[self.axis_tip_site_id]
        axis = tip - base
        norm = np.linalg.norm(axis)
        if norm < 1e-12:
            return WORLD_Z.copy()
        return axis / norm

    @staticmethod
    def tilt_angle_deg(cup_axis: np.ndarray) -> float:
        cos_angle = float(np.clip(np.dot(cup_axis, WORLD_Z), -1.0, 1.0))
        return float(np.degrees(np.arccos(cos_angle)))

    def jacobian_site(self, qpos: Iterable[float] | None = None) -> Tuple[np.ndarray, np.ndarray]:
        if qpos is not None:
            self.set_qpos(qpos)
        jacp = np.zeros((3, self.model.nv), dtype=float)
        jacr = np.zeros((3, self.model.nv), dtype=float)
        mujoco.mj_jacSite(self.model, self.data, jacp, jacr, self.ee_site_id)
        return jacp[:, self.dof_addr].copy(), jacr[:, self.dof_addr].copy()

    def normalized_limit_distance(self, qpos: Iterable[float]) -> np.ndarray:
        qpos_array = np.asarray(qpos, dtype=float)
        return (qpos_array - self.center) / np.maximum(self.span, 1e-9)


def smoothstep(values: np.ndarray) -> np.ndarray:
    """Cubic time scaling with zero velocity at both ends."""

    x = np.clip(np.asarray(values, dtype=float), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)
