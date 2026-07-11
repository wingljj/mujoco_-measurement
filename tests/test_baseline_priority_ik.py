import sys
import unittest
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baseline_priority_ik import finite_difference_jacobian, summarize_results


class PriorityIKUtilityTests(unittest.TestCase):
    def test_finite_difference_jacobian_matches_linear_map(self):
        matrix = np.array([[1.0, 2.0, 0.0], [0.0, -1.0, 3.0]])
        qpos = np.array([0.2, -0.3, 0.4])

        jacobian = finite_difference_jacobian(lambda q: matrix @ q, qpos, step=5e-5)

        np.testing.assert_allclose(jacobian, matrix, atol=1e-9)

    def test_summary_matches_ablation_schema(self):
        rows = [
            {
                "planned_success": True,
                "sim_success": True,
                "final_error_m": 0.01,
                "max_tilt_deg": 2.0,
                "plan_time_s": 0.2,
                "plan_nfev": 45,
            },
            {
                "planned_success": False,
                "sim_success": False,
                "final_error_m": float("nan"),
                "max_tilt_deg": float("nan"),
                "plan_time_s": 0.3,
                "plan_nfev": 60,
            },
        ]

        summary = summarize_results(rows)

        self.assertEqual(summary["variant"], "priority_ik")
        self.assertEqual(summary["total_targets"], 2)
        self.assertEqual(summary["ik_reachable"], 1)
        self.assertEqual(summary["sim_success"], 1)
        self.assertEqual(summary["sim_success_of_total_pct"], 50.0)
        self.assertEqual(
            list(summary),
            [
                "variant",
                "total_targets",
                "ik_reachable",
                "ik_reachability_pct",
                "sim_success",
                "sim_success_of_reachable_pct",
                "sim_success_of_total_pct",
                "mean_final_error_m",
                "max_final_error_m",
                "mean_max_tilt_deg",
                "max_max_tilt_deg",
                "mean_plan_time_s",
                "mean_plan_nfev",
            ],
        )

    def test_summary_safety_metrics_include_failed_executed_simulations(self):
        rows = [
            {
                "planned_success": True,
                "sim_success": True,
                "final_error_m": 0.01,
                "max_tilt_deg": 2.0,
                "plan_time_s": 0.2,
                "plan_nfev": 45,
            },
            {
                "planned_success": True,
                "sim_success": False,
                "final_error_m": 0.03,
                "max_tilt_deg": 20.0,
                "plan_time_s": 0.3,
                "plan_nfev": 60,
            },
        ]

        summary = summarize_results(rows)

        self.assertEqual(summary["sim_success"], 1)
        self.assertAlmostEqual(summary["mean_final_error_m"], 0.02)
        self.assertEqual(summary["max_final_error_m"], 0.03)
        self.assertAlmostEqual(summary["mean_max_tilt_deg"], 11.0)
        self.assertEqual(summary["max_max_tilt_deg"], 20.0)


if __name__ == "__main__":
    unittest.main()
