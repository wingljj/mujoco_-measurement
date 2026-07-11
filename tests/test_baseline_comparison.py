import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baseline_comparison import ABLATION_VARIANTS, summarize_results


class TightTiltVariantTests(unittest.TestCase):
    def test_tight_tilt_variants_only_differ_by_barrier_toggle(self):
        full = ABLATION_VARIANTS["full_tight10"]
        no_barrier = ABLATION_VARIANTS["no_barrier_tight10"]

        self.assertTrue(full.use_position)
        self.assertTrue(full.use_orientation)
        self.assertTrue(full.use_tilt_barrier)
        self.assertTrue(full.use_continuity)
        self.assertTrue(full.use_limit)

        self.assertTrue(no_barrier.use_position)
        self.assertTrue(no_barrier.use_orientation)
        self.assertFalse(no_barrier.use_tilt_barrier)
        self.assertTrue(no_barrier.use_continuity)
        self.assertTrue(no_barrier.use_limit)

    def test_summary_safety_metrics_include_failed_executed_simulations(self):
        rows = [
            {
                "planned_success": True,
                "sim_success": True,
                "final_error_m": 0.01,
                "max_tilt_deg": 2.0,
                "plan_time_s": 0.1,
                "plan_nfev": 10,
            },
            {
                "planned_success": True,
                "sim_success": False,
                "final_error_m": 0.03,
                "max_tilt_deg": 20.0,
                "plan_time_s": 0.1,
                "plan_nfev": 10,
            },
        ]

        summary = summarize_results(rows, "full_method")

        self.assertEqual(summary["sim_success"], 1)
        self.assertAlmostEqual(summary["mean_final_error_m"], 0.02)
        self.assertEqual(summary["max_final_error_m"], 0.03)
        self.assertAlmostEqual(summary["mean_max_tilt_deg"], 11.0)
        self.assertEqual(summary["max_max_tilt_deg"], 20.0)


if __name__ == "__main__":
    unittest.main()
