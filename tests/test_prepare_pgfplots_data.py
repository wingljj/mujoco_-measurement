import csv
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prepare_pgfplots_data import (  # noqa: E402
    _write_baselines,
    as_bool,
    empirical_cdf,
    histogram_rows,
    read_csv,
    select_representative_target,
    write_csv,
)


class PreparePgfplotsDataTests(unittest.TestCase):
    def test_as_bool_accepts_only_supported_truthy_spellings(self):
        for value in ("True", " true ", "1", "YES", "yes"):
            with self.subTest(value=value):
                self.assertTrue(as_bool(value))
        for value in ("False", "0", "no", "", "anything"):
            with self.subTest(value=value):
                self.assertFalse(as_bool(value))

    def test_read_and_write_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "data.csv"
            rows = [{"name": "仪器", "value": 2}]
            write_csv(path, ["name", "value"], rows)
            self.assertEqual(read_csv(path), [{"name": "仪器", "value": "2"}])

    def test_selects_successful_case_nearest_median_error(self):
        rows = [
            {"target_id": "0", "sim_success": "True", "final_error_m": "0.002"},
            {"target_id": "1", "sim_success": "False", "final_error_m": "0.004"},
            {"target_id": "2", "sim_success": "True", "final_error_m": "0.006"},
            {"target_id": "3", "sim_success": "True", "final_error_m": "0.010"},
        ]
        self.assertEqual(select_representative_target(rows), 2)

    def test_representative_selection_breaks_ties_by_target_id(self):
        rows = [
            {"target_id": "9", "sim_success": "True", "final_error_m": "0.001"},
            {"target_id": "4", "sim_success": "True", "final_error_m": "0.003"},
        ]
        self.assertEqual(select_representative_target(rows), 4)

    def test_empirical_cdf_is_sorted_finite_and_inclusive(self):
        values = empirical_cdf([3.0, float("nan"), 1.0, float("inf"), 2.0])
        self.assertEqual(values, [(1.0, 1 / 3), (2.0, 2 / 3), (3.0, 1.0)])

    def test_histogram_rows_preserve_count(self):
        rows = histogram_rows([1.0, 1.2, 1.8, 2.1], bins=2, log_scale=False)
        self.assertEqual(sum(row["count"] for row in rows), 4)
        self.assertTrue(all(row["left"] < row["right"] for row in rows))

    def test_log_histogram_rejects_nonpositive_values(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            histogram_rows([0.0, 1.0], bins=3, log_scale=True)

    def test_workspace_sources_have_expected_cardinality(self):
        root = Path(__file__).resolve().parents[1]
        expanded = read_csv(
            root / "outputs/round2_experiments/expanded_workspace_results.csv"
        )
        full = read_csv(root / "outputs/ablation_study/full_method_results.csv")
        priority = read_csv(
            root / "outputs/external_baselines/priority_ik_results.csv"
        )
        self.assertEqual(len(expanded), 80)
        self.assertEqual(len(full), 150)
        self.assertEqual(len(priority), 150)
        self.assertEqual(
            {row["target_id"] for row in full},
            {row["target_id"] for row in priority},
        )

    def test_baseline_export_preserves_all_150_paired_source_rows(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            _write_baselines(root, output)
            exported = read_csv(output / "fig08_baselines.csv")
        self.assertEqual(len(exported), 300)
        self.assertEqual(
            sum(row["method_cn"] == "本文方法" for row in exported), 150
        )
        self.assertEqual(
            sum(row["method_cn"] == "优先级IK" for row in exported), 150
        )


if __name__ == "__main__":
    unittest.main()
