import sys
import os
import re
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
COMPLETE_THEODOLITE_THEME = """# 经纬仪测站转移
本文研究刚性负载代理仿真。
仪器在机械臂到达目标位姿并稳定后测量。
10° 是本文研究设定的保守运输姿态报告阈值，不代表任何具体仪器的工作容差。
20 mm 是本目标集的任务特定位置判据。
本文未执行真实标定，也未建立运输倾角到测量结果的映射。
历史复现路径为 kuka_kr20/kuka_kr20_cup_transport.xml。
"""


class DataIntegrityParserTests(unittest.TestCase):
    @staticmethod
    def _create_full_root(root: Path) -> None:
        manuscript_path = root / "docs" / "theory_and_simulation.md"
        csv_path = root / "outputs" / "ablation_study" / "ablation_summary.csv"
        manuscript_path.parent.mkdir(parents=True)
        csv_path.parent.mkdir(parents=True)
        manuscript_path.write_text(
            COMPLETE_THEODOLITE_THEME
            + """
| 变体 | IK 规划 | 仿真成功 | 成功率 | 结论 |
|---|---|---|---|---|
| 完整方法 | 148/150 | 147/150 | 98.0% | 基线 |
| 无倾角屏障 | 148/150 | 147/150 | 98.0% | 同分 |
| 纯位置 | 45/150 | 45/150 | 30.0% | 可达率下降 |
| 位置+姿态 | 150/150 | 144/150 | 96.0% | 少量失败 |
""",
            encoding="utf-8",
        )
        csv_path.write_text(
            "variant,sim_success_of_total_pct\n"
            "full_method,98.0\n"
            "no_tilt_barrier,98.0\n"
            "position_only,30.0\n"
            "position_orientation,96.0\n",
            encoding="utf-8",
        )
        FigureOutputTests._create_outputs(root)

    @staticmethod
    def _run_cli(root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        repository_root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [
                sys.executable,
                str(
                    repository_root
                    / "review-stage"
                    / "round2_review"
                    / "check_data_integrity.py"
                ),
                "--root",
                str(root),
                *arguments,
            ],
            cwd=repository_root,
            capture_output=True,
            text=False,
            check=False,
        )

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

    def test_strict_full_cli_passes_complete_root_and_fails_missing_pair(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_full_root(root)

            complete = self._run_cli(root, "--strict")
            self.assertEqual(complete.returncode, 0, complete.stdout.decode("utf-8"))

            missing = root / "figures" / "pgfplots" / "build" / "fig08_baseline_comparison.pdf"
            missing.unlink()
            incomplete = self._run_cli(root, "--strict")
            output = incomplete.stdout.decode("utf-8")
            self.assertEqual(incomplete.returncode, 1, output)
            self.assertIn("fig08_baseline_comparison.pdf", output)

    def test_strict_cli_rejects_rate_difference_allowed_by_default(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_full_root(root)
            csv_path = root / "outputs" / "ablation_study" / "ablation_summary.csv"
            csv_path.write_text(
                csv_path.read_text(encoding="utf-8").replace(
                    "full_method,98.0", "full_method,98.5"
                ),
                encoding="utf-8",
            )

            tolerant = self._run_cli(root, "--rates-only")
            strict = self._run_cli(root, "--strict", "--rates-only")

            self.assertEqual(tolerant.returncode, 0, tolerant.stdout.decode("utf-8"))
            self.assertEqual(strict.returncode, 1, strict.stdout.decode("utf-8"))

    def test_cli_help_distinguishes_full_and_rates_only_modes(self):
        help_text = check_data_integrity.build_parser().format_help()

        self.assertIn("full rates, manuscript-theme, and figure-output checks", help_text)
        self.assertIn("explicit diagnostic bypass", help_text)
        self.assertIn("--root", help_text)


class ManuscriptThemeTests(unittest.TestCase):
    def test_old_theme_terms_are_reported_with_line_numbers(self):
        manuscript = """刚性负载代理仿真
持杯任务
杯体姿态
防洒约束
倾洒风险
液体晃动
容器运输
历史复现文件 kuka_kr20/kuka_kr20_cup_transport.xml
到达目标位姿并稳定后测量。
10° 是本文研究设定的保守运输姿态报告阈值，不代表具体仪器的工作容差。
20 mm 是任务特定位置判据。
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
        self.assertEqual(check_manuscript_theme(COMPLETE_THEODOLITE_THEME), [])

    def test_path_input_is_supported(self):
        manuscript = """本文采用刚性负载代理。
仪器到达目标位姿并稳定后才开始测量。
10° 是本文研究设定的保守运输阈值，不代表仪器工作容差。
20 mm 是任务特定位置判据。
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

    def test_threshold_claims_must_be_coherent_and_task_specific(self):
        manuscript = """本文研究刚性负载代理仿真。
仪器到达目标位姿并稳定后才开始测量。
10° 是制造商规定的测量精度阈值。
本文另有保守运输研究设定。
20 mm 是通用工程测量精度标准。
本文未执行真实标定，也未建立倾角到测量结果的映射。
"""

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("10°" in error for error in errors), errors)
        self.assertTrue(any("20 mm" in error for error in errors), errors)

    def test_later_instrument_threshold_claim_overrides_valid_boundary(self):
        manuscript = COMPLETE_THEODOLITE_THEME + "\n制造商规定 10° 为测量精度阈值。\n"

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("10°" in error for error in errors), errors)

    def test_later_positive_calibration_and_mapping_claims_are_rejected(self):
        manuscript = (
            COMPLETE_THEODOLITE_THEME
            + "\n项目随后完成了真实标定，并建立了倾角到测量误差映射。\n"
        )

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("真实标定" in error for error in errors), errors)
        self.assertTrue(any("测量结果映射" in error for error in errors), errors)

    def test_broader_legacy_terms_and_nonhistorical_cup_are_line_numbered(self):
        manuscript = COMPLETE_THEODOLITE_THEME + """
液体代理
独立晃动分析
sloshing benchmark
generic cup transport
"""

        errors = check_manuscript_theme(manuscript)

        for line_number, term in ((9, "液体"), (10, "晃动"), (11, "sloshing"), (12, "cup")):
            self.assertTrue(
                any(term in error.lower() and f"第 {line_number} 行" in error for error in errors),
                errors,
            )
        self.assertFalse(
            any("第 7 行" in error and "cup" in error.lower() for error in errors),
            errors,
        )

    def test_historical_cup_path_must_be_an_exact_token(self):
        manuscript = (
            COMPLETE_THEODOLITE_THEME
            + "\nprefixkuka_kr20/kuka_kr20_cup_transport.xmlsuffix\n"
        )

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(
            any("第 9 行" in error and "cup" in error.lower() for error in errors),
            errors,
        )

    def test_additional_threshold_contradictions_are_rejected(self):
        contradictory_claims = (
            ("10° 被某制造商用作测量精度。", "10°"),
            ("10° 源自行业测量精度要求。", "10°"),
            ("厂家规定 20 mm 为通用测量精度标准。", "20 mm"),
        )
        for claim, expected_error_text in contradictory_claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(
                    any(expected_error_text in error for error in errors),
                    errors,
                )

    def test_explicitly_negated_manufacturer_and_industry_boundaries_pass(self):
        manuscript = COMPLETE_THEODOLITE_THEME.replace(
            "10° 是本文研究设定的保守运输姿态报告阈值，不代表任何具体仪器的工作容差。",
            "10° 是本文研究设定的保守运输姿态报告阈值，并非制造商指标，也不是仪器测量精度标准。",
        ).replace(
            "20 mm 是本目标集的任务特定位置判据。",
            "20 mm 是任务特定位置判据，不代表行业测量精度标准。",
        )

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_additional_positive_calibration_and_mapping_claims_are_rejected(self):
        positive_claims = (
            ("随后完成了现场校准。", "真实标定"),
            ("随后实现了运输倾角与测量结果之间的映射。", "测量结果映射"),
        )
        for claim, expected_error_text in positive_claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(
                    any(expected_error_text in error for error in errors),
                    errors,
                )

    def test_clause_level_transport_contradiction_variants_are_rejected(self):
        claims = (
            "研究界限如下，10° 是制造商的精度限值。",
            "10° 是行业允许倾角。",
            "10° 是标准工作容差。",
            "10° 属于测量精度要求。",
            "10° 属于制造商测量精度限值。",
            "行业测量精度标准采用 10°。",
            "10° 是仪器制造商规定的测量精度阈值，20° 才是保守运输阈值",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(any("10°" in error for error in errors), errors)

    def test_clause_level_positive_calibration_actions_are_rejected(self):
        for action in ("开展", "完成", "执行", "进行", "实施", "获得", "验证", "采用"):
            claim = f"本文{action}真实标定。"
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(any("真实标定" in error for error in errors), errors)
        exact_claims = (
            "随后开展真实标定实验。",
            "随后完成真实标定。",
            "未执行仿真校准，随后完成了真实标定",
        )
        for claim in exact_claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(any("真实标定" in error for error in errors), errors)

    def test_clause_level_positive_mapping_actions_are_rejected(self):
        claims = (
            "本文建立倾角到测量结果的映射。",
            "本文给出倾角到测量结果的映射。",
            "通过数据得到倾角与测量误差关系。",
            "本文标定倾角与测量结果之间的映射。",
            "本文拟合倾角对精度的映射。",
            "随后建立运输倾角到测量结果的映射。",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(any("测量结果映射" in error for error in errors), errors)

    def test_clause_level_explicit_negations_remain_valid(self):
        manuscript = COMPLETE_THEODOLITE_THEME + """
10° 不是制造商允许倾角。
本文未开展真实标定。
本文没有给出倾角到测量结果的映射。
"""

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_non_negating_fei_words_do_not_hide_positive_claims(self):
        claims = (
            ("本文非常顺利地完成真实标定。", "真实标定"),
            ("本文建立倾角到测量结果的非线性映射。", "测量结果映射"),
        )
        for claim, expected_error_text in claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(
                    any(expected_error_text in error for error in errors),
                    errors,
                )

    def test_complete_is_a_positive_mapping_action(self):
        manuscript = COMPLETE_THEODOLITE_THEME + "\n本文完成倾角到测量结果的映射。\n"

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("测量结果映射" in error for error in errors), errors)

    def test_bare_fei_directly_negating_specification_remains_valid(self):
        manuscript = COMPLETE_THEODOLITE_THEME + "\n10° 非制造商允许倾角。\n"

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_contrastive_positive_suffixes_are_rejected(self):
        claims = (
            ("10° 不是研究设定而是制造商测量精度限值。", "10°"),
            ("本文并非仅开展仿真而是完成真实标定。", "真实标定"),
            ("本文没有停留在假设层面而是建立倾角到测量结果的映射。", "测量结果映射"),
        )
        for claim, expected_error_text in claims:
            with self.subTest(claim=claim):
                errors = check_manuscript_theme(COMPLETE_THEODOLITE_THEME + "\n" + claim)
                self.assertTrue(
                    any(expected_error_text in error for error in errors),
                    errors,
                )

    def test_contrastive_suffix_with_valid_study_setting_passes(self):
        manuscript = (
            COMPLETE_THEODOLITE_THEME
            + "\n10°不是制造商限值，而是本文保守运输研究设定。\n"
        )

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_contrast_anchor_does_not_leak_into_unrelated_comma_clause(self):
        manuscript = (
            COMPLETE_THEODOLITE_THEME
            + "\n10°不是制造商限值，但是本文采用标准符号书写。\n"
        )

        self.assertEqual(check_manuscript_theme(manuscript), [])

    def test_negation_after_positive_specification_does_not_hide_it(self):
        manuscript = (
            COMPLETE_THEODOLITE_THEME
            + "\n10°不是研究设定而是制造商测量精度限值并非本文研究设定。\n"
        )

        errors = check_manuscript_theme(manuscript)

        self.assertTrue(any("10°" in error for error in errors), errors)


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

    def test_unexpected_fig_outputs_are_reported_but_unrelated_files_are_allowed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            png_directory = root / "outputs" / "word_figures"
            pdf_directory = root / "figures" / "pgfplots" / "build"
            (png_directory / "fig09_legacy.png").write_bytes(b"png")
            (pdf_directory / "fig09_legacy.pdf").write_bytes(b"pdf")
            (png_directory / "README.txt").write_text("notes", encoding="utf-8")
            (pdf_directory / "build.log").write_text("log", encoding="utf-8")

            errors = check_figure_outputs(root)

            self.assertEqual(len(errors), 2, errors)
            self.assertTrue(any("fig09_legacy.png" in error for error in errors), errors)
            self.assertTrue(any("fig09_legacy.pdf" in error for error in errors), errors)
            self.assertTrue(all("意外" in error for error in errors), errors)

    def test_all_unexpected_image_outputs_are_reported_regardless_of_prefix(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            png_directory = root / "outputs" / "word_figures"
            pdf_directory = root / "figures" / "pgfplots" / "build"
            (png_directory / "legacy_cup_plot.png").write_bytes(b"png")
            (pdf_directory / "legacy_cup_plot.pdf").write_bytes(b"pdf")
            (png_directory / "README.txt").write_text("metadata", encoding="utf-8")

            errors = check_figure_outputs(root)

            self.assertEqual(len(errors), 2, errors)
            self.assertTrue(any("legacy_cup_plot.png" in error for error in errors), errors)
            self.assertTrue(any("legacy_cup_plot.pdf" in error for error in errors), errors)

    def test_non_file_collision_is_distinct_from_empty_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            collision = (
                root
                / "figures"
                / "pgfplots"
                / "build"
                / "fig06_error_tilt_margin.pdf"
            )
            collision.unlink()
            collision.mkdir()

            errors = check_figure_outputs(root)

            matching = [error for error in errors if collision.name in error]
            self.assertEqual(len(matching), 1, errors)
            self.assertIn("不是普通文件", matching[0])
            self.assertNotIn("空文件", matching[0])

    def test_image_outputs_in_wrong_managed_directory_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._create_outputs(root)
            word_directory = root / "outputs" / "word_figures"
            build_directory = root / "figures" / "pgfplots" / "build"
            (word_directory / "legacy_vector.pdf").write_bytes(b"pdf")
            (build_directory / "legacy_preview.png").write_bytes(b"png")

            errors = check_figure_outputs(root)

            self.assertEqual(len(errors), 2, errors)
            self.assertTrue(any("legacy_vector.pdf" in error for error in errors), errors)
            self.assertTrue(any("legacy_preview.png" in error for error in errors), errors)


class WordFigureGuideTests(unittest.TestCase):
    def test_png_is_primary_word_picture_and_pdf_is_vector_master(self):
        guide_path = (
            Path(__file__).resolve().parents[1]
            / "review-stage"
            / "round2_review"
            / "WORD_FIGURE_GUIDE.md"
        )
        guide = guide_path.read_text(encoding="utf-8")

        self.assertIn("600 DPI PNG 是 Word 插入的可靠主资产", guide)
        self.assertIn("插入 → 图片 → 此设备", guide)
        self.assertIn("选择对应 PNG", guide)
        self.assertIn("矢量主文件", guide)
        self.assertIn("插入 → 对象", guide)
        self.assertNotIn("优先选择对应 PDF", guide)
        self.assertNotIn("优先使用 `figures/pgfplots/build/` 中的矢量 PDF", guide)

    def test_caption_cells_contain_bodies_without_manual_figure_numbers(self):
        guide_path = (
            Path(__file__).resolve().parents[1]
            / "review-stage"
            / "round2_review"
            / "WORD_FIGURE_GUIDE.md"
        )
        guide = guide_path.read_text(encoding="utf-8")
        figure_rows = [
            line
            for line in guide.splitlines()
            if re.match(r"\| 图[1-8] \|", line) and line.count("|") == 6
        ]

        self.assertIn("题注正文（不含自动编号）", guide)
        self.assertEqual(len(figure_rows), 8)
        for row in figure_rows:
            caption_body = row.strip("|").split("|")[-1].strip()
            self.assertNotRegex(caption_body, r"^图\s*[1-8]")
        self.assertIn("Word 自动生成 `图 N`", guide)
        self.assertIn("只粘贴题注正文", guide)
        self.assertIn("不要手工输入图号", guide)


if __name__ == "__main__":
    unittest.main()
