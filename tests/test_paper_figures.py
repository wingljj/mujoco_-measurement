import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paper_figures import read_ablation_summary


class PaperFigureDataTests(unittest.TestCase):
    def test_read_ablation_summary_returns_numeric_success_rates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "summary.csv"
            path.write_text(
                "variant,sim_success_of_total_pct,ik_reachability_pct\n"
                "full_method,98.0,98.6666667\n"
                "no_tilt_barrier,98.0,98.6666667\n",
                encoding="utf-8",
            )

            rows = read_ablation_summary(path)

        self.assertEqual(rows[0]["variant"], "full_method")
        self.assertEqual(rows[0]["sim_rate_pct"], 98.0)
        self.assertAlmostEqual(rows[1]["ik_rate_pct"], 98.6666667)


if __name__ == "__main__":
    unittest.main()
