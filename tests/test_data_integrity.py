import sys
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "review-stage"
        / "round2_review"
    ),
)

import check_data_integrity


parse_paper_rates = check_data_integrity.parse_paper_rates
check_manuscript_theme = check_data_integrity.check_manuscript_theme
check_figure_outputs = check_data_integrity.check_figure_outputs

FIGURE_BASENAMES = (
    "fig01_method_pipeline",
    "fig02_workspace_multiview",
    "fig03_transport_sequence",
    "fig04_case_study",
    "fig05_ablation_comparison",
    "fig06_error_tilt_margin",
    "fig07_dynamic_metrics",
    "fig08_baseline_comparison",
)


class DataIntegrityParserTests(unittest.TestCase):
    def test_parse_paper_rates_reads_four_default_ablation_rows(self):
        manuscript = """
### 4.2 结果
| 变体 | IK 规划 | 仿真成功 | 成功率 | 结论 |
|---|---|---|---|---|
| **完整方法** | 148/150 | **147/150** | **98.0%** | 基线 |
| 无倾角屏障 | 148/150 | 147/150 | 98.0% | 同分 |
| 纯位置 | 45/150 | 45/150 | 30.0% | 可达率下降 |
| 位置+姿态 | 150/150 | 144/150 | 96.0% | 少量失败 |
"""

        rates = parse_paper_rates(manuscript)

        self.assertEqual(
            rates,
            {
                "full_method": 98.0,
                "no_tilt_barrier": 98.0,
                "position_only": 30.0,
                "position_orientation": 96.0,
            },
        )

    def test_cli_handles_legacy_windows_stdout_encoding(self):
        root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "gbk"

        result = subprocess.run(
            [
                sys.executable,
                "review-stage/round2_review/check_data_integrity.py",
                "--strict",
                "--rates-only",
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=False,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode("gbk", errors="replace"))


class ManuscriptThemeTests(unittest.TestCase):
    def test_old_theme_terms_are_reported_with_line_numbers(self):
        manuscript = """刚性负载代理仿真
持杯任务
杯体姿态
防洒约束
倾洒风险
液体晃动
容器运输
历史复现文件 kuka_kr20_cup_transport.xml
到达目标位姿并稳定后测量，采用 10° 保守运输阈值。
本文未执行真实标定，也未建立运输倾角到测量结果的映射。
"""

        errors = check_manuscript_theme(manuscript)

        for line_number, term in enumerate(
            ("持杯", "杯体", "防洒", "倾洒", "液体晃动", "容器运输"), start=2
        ):
            self.assertTrue(
                any(term in error and f"第 {line_number} 行" in error for error in errors),
                errors,
            )
        self.assertFalse(any("cup" in error for error in errors), errors)

    def test_complete_theodolite_fixture_passes(self):
        manuscript = """# 经纬仪测站转移
本文研究刚性负载代理仿真。
仪器在机械臂到达目标位姿并稳定后测量。
10° 是本文的保守运输姿态报告阈值。
本文未执行真实标定，也未建立运输倾角到测量结果的映射。
"""

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_path_input_is_supported(self):
        manuscript = """本文采用刚性负载代理。
仪器到达目标位姿并稳定后才开始测量。
10° 是保守运输阈值。
本文不包含真实标定，也没有运输倾角到测量结果的映射。
"""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "paper.md"
            path.write_text(manuscript, encoding="utf-8")

            self.assertEqual(check_manuscript_theme(path), [])

    def test_opposite_proxy_and_measurement_claims_are_rejected(self):
        manuscript = """本文采用真实刚性负载代理实验。
机械臂到达目标位姿并稳定后继续运输，测量则在运动中进行。
10° 是保守运输阈值。
本文未执行真实标定，也未建立倾角到测量结果的映射。
"""

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("刚性负载代理仿真" in error for error in errors), errors)
        self.assertTrue(any("稳定后测量" in error for error in errors), errors)

    def test_double_negative_boundaries_are_rejected(self):
        manuscript = """本文研究刚性负载代理仿真。
仪器到达目标位姿并稳定后才开始测量。
10° 是保守运输阈值。
本文不缺少真实标定，也不缺少倾角到测量结果的映射。
"""

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("真实标定" in error for error in errors), errors)
        self.assertTrue(any("测量结果映射" in error for error in errors), errors)


class FigureOutputTests(unittest.TestCase):
    @staticmethod
    def _create_outputs(root: Path) -> None:
        png_directory = root / "outputs" / "word_figures"
        pdf_directory = root / "figures" / "pgfplots" / "build"
        png_directory.mkdir(parents=True)
        pdf_directory.mkdir(parents=True)
        for basename in FIGURE_BASENAMES:
            (png_directory / f"{basename}.png").write_bytes(b"png")
            (pdf_directory / f"{basename}.pdf").write_bytes(b"pdf")

    def test_all_eight_nonempty_png_and_pdf_pairs_pass(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)

            self.assertEqual(check_figure_outputs(root), [])

    def test_missing_managed_output_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            missing = root / "outputs" / "word_figures" / "fig03_transport_sequence.png"
            missing.unlink()

            errors = check_figure_outputs(root)

            self.assertTrue(any("fig03_transport_sequence.png" in error for error in errors), errors)
            self.assertTrue(any("缺少" in error for error in errors), errors)

    def test_empty_managed_output_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            empty = root / "figures" / "pgfplots" / "build" / "fig06_error_tilt_margin.pdf"
            empty.write_bytes(b"")

            errors = check_figure_outputs(root)

            self.assertTrue(any("fig06_error_tilt_margin.pdf" in error for error in errors), errors)
            self.assertTrue(any("空文件" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
