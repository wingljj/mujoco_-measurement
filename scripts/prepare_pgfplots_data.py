"""Prepare traceable CSV inputs for the manuscript's pgfplots figures."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "figures" / "pgfplots" / "data"

REGION_NAMES = {
    "standard": "标准区",
    "wide_azimuth": "宽方位角区",
    "low_reach": "低伸区",
    "high_reach": "高伸区",
    "far_reach": "远距离区",
}
ABLATION_NAMES = {
    "full_method": "完整方法",
    "no_tilt_barrier": "无倾角屏障",
    "position_only": "纯位置",
    "position_orientation": "位置+姿态",
}
BASELINE_NAMES = {
    "full_method": "本文方法",
    "priority_ik": "优先级IK",
}


def as_bool(value: str) -> bool:
    """Interpret the supported truthy spellings used by the source CSVs."""
    return value.strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV as string-valued dictionaries."""
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, object]],
) -> None:
    """Write dictionaries to a UTF-8 CSV, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def select_representative_target(rows: list[dict[str, str]]) -> int:
    """Return the successful target closest to median final position error."""
    successful = []
    for row in rows:
        error_text = row.get("final_error_m", "")
        try:
            error = float(error_text)
        except (TypeError, ValueError):
            continue
        if as_bool(row.get("sim_success", "")) and np.isfinite(error):
            successful.append((row, error))
    if not successful:
        raise ValueError("no successful simulation rows with finite final error")
    median = float(np.median([error for _, error in successful]))
    selected, _ = min(
        successful,
        key=lambda item: (abs(item[1] - median), int(item[0]["target_id"])),
    )
    return int(selected["target_id"])


def empirical_cdf(values: Iterable[float]) -> list[tuple[float, float]]:
    """Return finite values in ascending order with inclusive empirical ranks."""
    ordered = sorted(float(value) for value in values if np.isfinite(value))
    if not ordered:
        raise ValueError("ECDF requires finite values")
    count = len(ordered)
    return [(value, (index + 1) / count) for index, value in enumerate(ordered)]


def histogram_rows(
    values: Iterable[float],
    bins: int,
    log_scale: bool,
) -> list[dict[str, float | int]]:
    """Bin finite values on linear or positive logarithmic edges."""
    if bins < 1:
        raise ValueError("histogram bins must be positive")
    array = np.asarray(
        [float(value) for value in values if np.isfinite(value)], dtype=float
    )
    if array.size == 0:
        raise ValueError("histogram requires finite values")
    if log_scale and np.any(array <= 0):
        raise ValueError("log histogram values must be positive")

    minimum = float(array.min())
    maximum = float(array.max())
    if minimum == maximum:
        if log_scale:
            edges = np.geomspace(minimum * 0.9, maximum * 1.1, bins + 1)
        else:
            padding = max(abs(minimum) * 0.1, 0.5)
            edges = np.linspace(minimum - padding, maximum + padding, bins + 1)
    elif log_scale:
        edges = np.geomspace(minimum * 0.9, maximum * 1.1, bins + 1)
    else:
        edges = np.linspace(minimum, maximum, bins + 1)

    counts, edges = np.histogram(array, bins=edges)
    return [
        {
            "left": float(edges[index]),
            "right": float(edges[index + 1]),
            "center": float((edges[index] + edges[index + 1]) / 2),
            "count": int(counts[index]),
        }
        for index in range(len(counts))
    ]


def _finite_float(value: str) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if np.isfinite(converted) else None


def _float_or_nan(value: str, scale: float = 1.0) -> float:
    converted = _finite_float(value)
    return float("nan") if converted is None else converted * scale


def _write_workspace(root: Path, out: Path) -> None:
    source = read_csv(
        root / "outputs" / "round2_experiments" / "expanded_workspace_results.csv"
    )
    unknown_regions = {row["region"] for row in source} - REGION_NAMES.keys()
    if unknown_regions:
        raise ValueError(f"unknown workspace regions: {sorted(unknown_regions)}")
    rows = [
        {
            "target_id": row["target_id"],
            "region_cn": REGION_NAMES[row["region"]],
            "x": row["target_x"],
            "y": row["target_y"],
            "z": row["target_z"],
            "sim_success": row["sim_success"],
            "max_tilt_deg": row["max_tilt_deg"],
        }
        for row in source
    ]
    write_csv(
        out / "fig02_workspace.csv",
        ["target_id", "region_cn", "x", "y", "z", "sim_success", "max_tilt_deg"],
        rows,
    )


def _write_case_study(root: Path, out: Path) -> None:
    results = read_csv(root / "outputs" / "experiment_001" / "results.csv")
    target_id = select_representative_target(results)
    result_by_id = {int(row["target_id"]): row for row in results}
    selected = result_by_id[target_id]

    archive_path = root / "outputs" / "experiment_001" / "trajectories.npz"
    with np.load(archive_path, allow_pickle=True) as archive:
        planned_ee = np.asarray(archive["planned_ee"][target_id], dtype=float)
        planned_qpos = np.asarray(archive["planned_qpos"][target_id], dtype=float)
        sim_tilt = np.asarray(archive["sim_tilt"][target_id], dtype=float)
        sim_time = np.asarray(archive["sim_time"][target_id], dtype=float)

    if planned_ee.ndim != 2 or planned_ee.shape[1] != 3:
        raise ValueError("representative planned_ee must have shape (n, 3)")
    if planned_qpos.shape != (len(planned_ee), 6):
        raise ValueError("representative planned_qpos must align with planned_ee")
    if sim_time.shape != sim_tilt.shape:
        raise ValueError("representative sim_time and sim_tilt must align")

    target = np.asarray(
        [selected["target_x"], selected["target_y"], selected["target_z"]],
        dtype=float,
    )
    progress = np.linspace(0.0, 1.0, len(planned_ee))
    smoothstep = 3.0 * progress**2 - 2.0 * progress**3
    desired = planned_ee[0] + smoothstep[:, None] * (target - planned_ee[0])
    ik_error_mm = np.linalg.norm(planned_ee - desired, axis=1) * 1000.0

    write_csv(
        out / "fig04_meta.csv",
        [
            "target_id",
            "target_x",
            "target_y",
            "target_z",
            "final_error_mm",
            "max_tilt_deg",
        ],
        [
            {
                "target_id": target_id,
                "target_x": selected["target_x"],
                "target_y": selected["target_y"],
                "target_z": selected["target_z"],
                "final_error_mm": float(selected["final_error_m"]) * 1000.0,
                "max_tilt_deg": selected["max_tilt_deg"],
            }
        ],
    )
    write_csv(
        out / "fig04_trajectory.csv",
        [
            "sample",
            "x",
            "y",
            "z",
            "desired_x",
            "desired_y",
            "desired_z",
            "ik_error_mm",
        ],
        [
            {
                "sample": index,
                "x": point[0],
                "y": point[1],
                "z": point[2],
                "desired_x": desired[index, 0],
                "desired_y": desired[index, 1],
                "desired_z": desired[index, 2],
                "ik_error_mm": ik_error_mm[index],
            }
            for index, point in enumerate(planned_ee)
        ],
    )
    write_csv(
        out / "fig04_joints.csv",
        ["sample", "q1", "q2", "q3", "q4", "q5", "q6"],
        [
            {"sample": index, **{f"q{joint + 1}": value for joint, value in enumerate(q)}}
            for index, q in enumerate(planned_qpos)
        ],
    )
    write_csv(
        out / "fig04_tilt.csv",
        ["time_s", "tilt_deg"],
        [
            {"time_s": time, "tilt_deg": tilt}
            for time, tilt in zip(sim_time, sim_tilt, strict=True)
        ],
    )


def _write_ablation(root: Path, out: Path) -> None:
    source = read_csv(root / "outputs" / "ablation_study" / "ablation_summary.csv")
    by_variant = {row["variant"]: row for row in source}
    if set(by_variant) != set(ABLATION_NAMES):
        raise ValueError("ablation variants do not match the expected four methods")
    rows = [
        {
            "method_cn": method_cn,
            "ik_rate_pct": by_variant[variant]["ik_reachability_pct"],
            "sim_rate_pct": by_variant[variant]["sim_success_of_total_pct"],
        }
        for variant, method_cn in ABLATION_NAMES.items()
    ]
    write_csv(
        out / "fig05_ablation.csv",
        ["method_cn", "ik_rate_pct", "sim_rate_pct"],
        rows,
    )


def _write_ecdfs(root: Path, out: Path) -> None:
    source = read_csv(root / "outputs" / "ablation_study" / "full_method_results.csv")
    executed = [
        row
        for row in source
        if as_bool(row["planned_success"])
        and _finite_float(row["final_error_m"]) is not None
        and _finite_float(row["max_tilt_deg"]) is not None
    ]
    series = {
        "fig06_error_ecdf.csv": [float(row["final_error_m"]) * 1000 for row in executed],
        "fig06_tilt_ecdf.csv": [float(row["max_tilt_deg"]) for row in executed],
        "fig06_margin_ecdf.csv": [10.0 - float(row["max_tilt_deg"]) for row in executed],
    }
    for filename, values in series.items():
        write_csv(
            out / filename,
            ["value", "cdf"],
            [
                {"value": value, "cdf": cdf}
                for value, cdf in empirical_cdf(values)
            ],
        )


def _write_histograms(root: Path, out: Path) -> None:
    source = read_csv(
        root / "outputs" / "round2_experiments" / "dynamic_metrics_results.csv"
    )
    specifications = [
        ("accel", "dyn_max_accel", 10, False),
        ("max_jerk", "dyn_max_jerk", 9, True),
        ("max_ang_vel", "dyn_max_ang_vel", 9, True),
        ("avg_ang_vel", "dyn_avg_ang_vel", 9, True),
    ]
    output_rows: list[dict[str, object]] = []
    for metric, column, bins, log_scale in specifications:
        values = [
            value
            for row in source
            if (value := _finite_float(row[column])) is not None
        ]
        median = float(np.median(values))
        for histogram in histogram_rows(values, bins=bins, log_scale=log_scale):
            output_rows.append(
                {
                    "metric": metric,
                    **histogram,
                    "median": median,
                    "log_scale": str(log_scale).lower(),
                }
            )
    write_csv(
        out / "fig07_histograms.csv",
        ["metric", "left", "right", "center", "count", "median", "log_scale"],
        output_rows,
    )


def _write_baselines(root: Path, out: Path) -> None:
    full = read_csv(root / "outputs" / "ablation_study" / "full_method_results.csv")
    priority = read_csv(
        root / "outputs" / "external_baselines" / "priority_ik_results.csv"
    )
    priority_by_id: dict[int, list[dict[str, str]]] = {}
    for row in priority:
        priority_by_id.setdefault(int(row["target_id"]), []).append(row)
    occurrence_by_id: dict[int, int] = {}
    rows = []
    for full_row in full:
        target_id = int(full_row["target_id"])
        occurrence = occurrence_by_id.get(target_id, 0)
        priority_matches = priority_by_id.get(target_id, [])
        if occurrence >= len(priority_matches):
            continue
        priority_row = priority_matches[occurrence]
        occurrence_by_id[target_id] = occurrence + 1
        full_coordinates = tuple(full_row[f"target_{axis}"] for axis in "xyz")
        priority_coordinates = tuple(priority_row[f"target_{axis}"] for axis in "xyz")
        if full_coordinates != priority_coordinates:
            raise ValueError(
                f"baseline target {target_id} occurrence {occurrence} coordinates differ"
            )
        for source, variant in (
            (full_row, "full_method"),
            (priority_row, "priority_ik"),
        ):
            rows.append(
                {
                    "target_id": target_id,
                    "method_cn": BASELINE_NAMES[variant],
                    "error_mm": _float_or_nan(source["final_error_m"], 1000.0),
                    "tilt_deg": _float_or_nan(source["max_tilt_deg"]),
                    "sim_success": source["sim_success"],
                }
            )
    write_csv(
        out / "fig08_baselines.csv",
        ["target_id", "method_cn", "error_mm", "tilt_deg", "sim_success"],
        rows,
    )


def prepare_data(root: Path, out: Path) -> None:
    """Generate all eleven pgfplots source CSVs from immutable experiment data."""
    _write_workspace(root, out)
    _write_case_study(root, out)
    _write_ablation(root, out)
    _write_ecdfs(root, out)
    _write_histograms(root, out)
    _write_baselines(root, out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> None:
    arguments = build_parser().parse_args()
    prepare_data(arguments.root.resolve(), arguments.out.resolve())


if __name__ == "__main__":
    main()
