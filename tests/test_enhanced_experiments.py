import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from enhanced_experiments import summarize_sensitivity_sim


class SensitivitySimulationSummaryTests(unittest.TestCase):
    def test_summary_groups_by_parameter_and_value(self):
        rows = [
            {
                "param": "orientation_weight",
                "value": 0.9,
                "ik_ok": True,
                "sim_ok": True,
                "max_tilt_deg": 1.0,
            },
            {
                "param": "orientation_weight",
                "value": 0.9,
                "ik_ok": True,
                "sim_ok": False,
                "max_tilt_deg": 3.0,
            },
            {
                "param": "orientation_weight",
                "value": 1.8,
                "ik_ok": False,
                "sim_ok": False,
                "max_tilt_deg": float("nan"),
            },
        ]

        summary = summarize_sensitivity_sim(rows)

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["param"], "orientation_weight")
        self.assertEqual(summary[0]["value"], 0.9)
        self.assertEqual(summary[0]["ik_rate_pct"], 100.0)
        self.assertEqual(summary[0]["sim_rate_pct"], 50.0)
        self.assertEqual(summary[0]["mean_max_tilt"], 2.0)
        self.assertEqual(summary[1]["ik_rate_pct"], 0.0)
        self.assertEqual(summary[1]["sim_rate_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
