"""Validate manuscript rates, theme boundaries, and exact managed figure outputs.

The default mode and ``--strict`` run the full rates, manuscript-theme, and
figure-output checks. ``--rates-only`` is an explicit diagnostic bypass for
early-stage rate verification.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
VARIANT_NAMES = {
    "完整方法": "full_method",
    "无倾角屏障": "no_tilt_barrier",
    "纯位置": "position_only",
    "位置+姿态": "position_orientation",
}
LEGACY_THEME_TERMS = (
    "持杯",
    "杯体",
    "防洒",
    "倾洒",
    "液体晃动",
    "容器运输",
    "液体",
    "晃动",
    "sloshing",
)
ALLOWED_HISTORICAL_CUP_PATH = "kuka_kr20/kuka_kr20_cup_transport.xml"
CLAUSE_NEGATIONS = ("不是", "不代表", "并非", "不能", "不得", "不应", "没有", "未")
TRANSPORT_SPEC_TERMS = (
    "制造商",
    "厂家",
    "行业",
    "标准",
    "测量精度",
    "精度限值",
    "允许倾角",
    "工作容差",
)
CALIBRATION_ACTIONS = ("开展", "完成", "执行", "进行", "实施", "获得", "验证", "采用")
CALIBRATION_TERMS = ("真实标定", "现场校准")
MAPPING_ACTIONS = ("建立", "给出", "得到", "标定", "拟合", "实现", "完成")
MAPPING_TARGETS = ("测量结果", "测量误差", "精度", "映射")
RIGID_PROXY_PHRASES = ("刚性负载代理", "刚性负载代理仿真")
STABLE_MEASUREMENT_PHRASES = (
    "到达目标位姿并稳定后测量",
    "到达目标位姿并稳定后才开始测量",
    "到位稳定后测量",
    "到位稳定后才开始测量",
    "到位并稳定后测量",
    "到位并稳定后才开始测量",
)
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
EXPECTED_MANUSCRIPT_IMAGES = (
    "fig01_method_pipeline.png",
    "rendered_transport_snapshots.png",
    "fig02_workspace_multiview.png",
    "trajectory_3d_render.png",
    "fig03_transport_sequence.png",
    "fig04_case_study.png",
    "fig05_ablation_comparison.png",
    "fig06_error_tilt_margin.png",
    "fig07_dynamic_metrics.png",
    "fig08_baseline_comparison.png",
)
RESTORED_MANUSCRIPT_IMAGES = (
    "rendered_transport_snapshots.png",
    "trajectory_3d_render.png",
)
RESTORED_FIGURE_DISCLAIMERS = ("简化刚性负载代理", "不代表真实经纬仪")


def parse_paper_rates(manuscript: str) -> dict[str, float]:
    """Extract the four default-ablation success rates from the §4.2 table."""
    lines = manuscript.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("|") and "IK 规划" in line and "仿真成功" in line
        ),
        None,
    )
    if header_index is None:
        raise ValueError("未找到包含‘IK 规划’和‘仿真成功’的 §4.2 表格。")

    rates: dict[str, float] = {}
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip().replace("**", "") for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        paper_name = cells[0]
        if paper_name not in VARIANT_NAMES:
            continue
        match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", cells[3])
        if not match:
            raise ValueError(f"无法从变体‘{paper_name}’的成功率单元格解析百分比。")
        rates[VARIANT_NAMES[paper_name]] = float(match.group(1))

    missing = set(VARIANT_NAMES.values()) - set(rates)
    if missing:
        raise ValueError(f"§4.2 表格缺少变体：{', '.join(sorted(missing))}")
    return rates


def read_csv_rates(path: Path) -> dict[str, float]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return {
            row["variant"]: float(row["sim_success_of_total_pct"])
            for row in csv.DictReader(handle)
            if row["variant"] in VARIANT_NAMES.values()
        }


def _read_path_or_text(path_or_text: Path | str) -> str:
    if isinstance(path_or_text, Path):
        return path_or_text.read_text(encoding="utf-8")
    if "\n" not in path_or_text and "\r" not in path_or_text:
        try:
            candidate = Path(path_or_text)
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            pass
    return path_or_text


def _split_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for sentence in re.split(r"[。！？!?；;\n]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_anchors: list[str] = []
        if "10°" in sentence:
            sentence_anchors.append("10°")
        if re.search(r"20\s*mm", sentence, flags=re.IGNORECASE):
            sentence_anchors.append("20 mm")
        for comma_unit in re.split(r"[，,]", sentence):
            comma_unit = comma_unit.strip()
            if not comma_unit:
                continue
            unit_anchors = [anchor for anchor in sentence_anchors if anchor in comma_unit]
            leading_contrast = re.match(r"(?:而是|但是|然而|不过|但|却)", comma_unit)
            strong_specification = any(
                term in comma_unit
                for term in (
                    "制造商",
                    "厂家",
                    "行业",
                    "测量精度",
                    "精度限值",
                    "允许倾角",
                    "工作容差",
                )
            )
            if not unit_anchors and leading_contrast and strong_specification:
                unit_anchors = sentence_anchors
            for clause in re.split(r"(?:而是|但是|然而|不过|但|却)", comma_unit):
                clause = clause.strip()
                if not clause:
                    continue
                inherited_anchors = [anchor for anchor in unit_anchors if anchor not in clause]
                clauses.append(" ".join((*inherited_anchors, clause)))
    return clauses


def _first_term_position(clause: str, terms: tuple[str, ...]) -> int | None:
    positions = [clause.find(term) for term in terms if term in clause]
    return min(positions) if positions else None


def _is_negated_before(clause: str, position: int) -> bool:
    prefix = clause[:position].rstrip()[-16:]
    return any(negation in prefix for negation in CLAUSE_NEGATIONS) or prefix.endswith(
        ("非", "无")
    )


def _has_unnegated_terms(clause: str, terms: tuple[str, ...]) -> bool:
    position = _first_term_position(clause, terms)
    return position is not None and not _is_negated_before(clause, position)


def check_manuscript_theme(path_or_text: Path | str) -> list[str]:
    """Return manuscript-theme errors, including line numbers for legacy terms."""
    manuscript = _read_path_or_text(path_or_text)
    errors: list[str] = []

    for line_number, line in enumerate(manuscript.splitlines(), start=1):
        lower_line = line.lower()
        for term in LEGACY_THEME_TERMS:
            if term.lower() in lower_line:
                errors.append(f"第 {line_number} 行包含旧主题词‘{term}’。")
        cup_check_line = re.sub(
            rf"(?<![a-z0-9_./-]){re.escape(ALLOWED_HISTORICAL_CUP_PATH)}"
            r"(?![a-z0-9_./-])",
            "",
            lower_line,
        )
        if re.search(r"(?<![a-z])cup(?![a-z])", cup_check_line):
            errors.append(f"第 {line_number} 行包含旧主题词‘cup’。")

    proxy_contradiction = re.search(
        r"(?:真实|实物)[^。；\n]{0,20}刚性负载代理(?:实验|试验)"
        r"|刚性负载代理[^。；\n]{0,20}(?:真实|实物)(?:实验|试验)",
        manuscript,
    )
    if (
        not any(phrase in manuscript for phrase in RIGID_PROXY_PHRASES)
        or proxy_contradiction is not None
    ):
        errors.append("正文缺少无矛盾的‘刚性负载代理仿真’研究对象说明。")
    if not any(phrase in manuscript for phrase in STABLE_MEASUREMENT_PHRASES):
        errors.append("正文缺少‘到达目标位姿并稳定后测量’的时序边界。")
    statements = [
        statement.strip()
        for statement in re.split(r"(?<=[。！？!?])|\n+", manuscript)
        if statement.strip()
    ]
    clauses = _split_clauses(manuscript)
    valid_transport_boundary = any(
        "10°" in statement
        and "保守运输" in statement
        and ("研究设定" in statement or "报告阈值" in statement)
        and re.search(
            r"(?:不代表|不是|并非)[^。；\n]{0,40}(?:仪器|性能规范|工作容差)",
            statement,
        )
        for statement in statements
    )
    contradictory_transport_boundary = any(
        "10°" in clause
        and _has_unnegated_terms(clause, TRANSPORT_SPEC_TERMS)
        for clause in clauses
    )
    if not valid_transport_boundary or contradictory_transport_boundary:
        errors.append(
            "正文缺少无矛盾的 10° 保守运输研究设定及非仪器容差边界。"
        )

    valid_position_boundary = any(
        re.search(r"20\s*mm", statement, flags=re.IGNORECASE)
        and "任务特定" in statement
        and "位置判据" in statement
        for statement in statements
    )
    contradictory_position_boundary = any(
        re.search(r"20\s*mm", clause, flags=re.IGNORECASE)
        and any(
            term in clause
            for term in ("制造商", "厂家", "行业", "通用", "标准", "测量精度")
        )
        and _has_unnegated_terms(
            clause,
            ("制造商", "厂家", "行业", "通用", "标准", "测量精度"),
        )
        for clause in clauses
    )
    if not valid_position_boundary or contradictory_position_boundary:
        errors.append("正文缺少‘20 mm 为任务特定位置判据’的边界。")

    calibration_pattern = re.compile(
        r"(?:未执行|未进行|未包含|未采用|未做|没有执行|没有进行|"
        r"没有包含|没有采用|不包含)[^。；\n]{0,50}(?:真实|实物)?"
        r"[^。；\n]{0,10}标定"
    )
    measurement_mapping_pattern = re.compile(
        r"(?:未建立|未包含|没有建立|没有包含|不包含)[^。；\n]{0,100}"
        r"(?:测量结果[^。；\n]{0,30}(?:映射|误差模型)|测量映射|"
        r"倾角[^。；\n]{0,50}(?:映射|误差模型))"
    )
    coherent_measurement_boundary = any(
        calibration_pattern.search(statement)
        and measurement_mapping_pattern.search(statement)
        for statement in statements
    )
    positive_calibration_claim = any(
        any(term in clause for term in CALIBRATION_TERMS)
        and any(action in clause for action in CALIBRATION_ACTIONS)
        and _has_unnegated_terms(clause, CALIBRATION_ACTIONS)
        for clause in clauses
    )
    positive_mapping_claim = any(
        "倾角" in clause
        and any(action in clause for action in MAPPING_ACTIONS)
        and any(target in clause for target in MAPPING_TARGETS)
        and _has_unnegated_terms(clause, MAPPING_ACTIONS)
        for clause in clauses
    )
    if not coherent_measurement_boundary or positive_calibration_claim:
        errors.append("正文缺少‘未做真实标定’的研究边界。")
    if not coherent_measurement_boundary or positive_mapping_claim:
        errors.append("正文缺少‘未建立运输倾角到测量结果映射’的研究边界。")

    return errors


def _renderable_markdown_lines(manuscript: str) -> list[str]:
    """Mask Markdown regions that cannot render as manuscript prose or images."""
    without_comments = re.sub(
        r"<!--.*?-->",
        lambda match: re.sub(r"[^\r\n]", " ", match.group(0)),
        manuscript,
        flags=re.DOTALL,
    )
    rendered_lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in without_comments.splitlines():
        fence = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence_character is not None:
            rendered_lines.append("")
            if (
                fence is not None
                and fence.group(1)[0] == fence_character
                and len(fence.group(1)) >= fence_length
            ):
                fence_character = None
            continue
        if fence is not None:
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            rendered_lines.append("")
            continue
        rendered_lines.append(re.sub(r"(`+).*?\1", "", line))
    return rendered_lines


def check_manuscript_figures(path_or_text: Path | str) -> list[str]:
    """Return errors for manuscript image order and restored-figure boundaries."""
    manuscript = _read_path_or_text(path_or_text)
    lines = _renderable_markdown_lines(manuscript)
    image_pattern = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
    images: list[tuple[str, int]] = []
    for line_number, line in enumerate(lines):
        for match in image_pattern.finditer(line):
            images.append((Path(match.group(1)).name, line_number))

    actual_names = [name for name, _line_number in images]
    errors: list[str] = []
    for name in RESTORED_MANUSCRIPT_IMAGES:
        if name not in actual_names:
            errors.append(f"正文缺少恢复图：{name}")
    if actual_names != list(EXPECTED_MANUSCRIPT_IMAGES):
        errors.append("正文图片顺序必须与规定的 10 幅图顺序完全一致。")

    for name in RESTORED_MANUSCRIPT_IMAGES:
        positions = [line_number for image_name, line_number in images if image_name == name]
        if not positions:
            continue
        line_number = positions[0]
        adjacent_lines: list[str] = []
        for direction in (-1, 1):
            index = line_number + direction
            while 0 <= index < len(lines) and not lines[index].strip():
                index += direction
            if 0 <= index < len(lines):
                adjacent_lines.append(lines[index])
        adjacent_text = " ".join(adjacent_lines)
        missing_phrases = [
            phrase for phrase in RESTORED_FIGURE_DISCLAIMERS if phrase not in adjacent_text
        ]
        if missing_phrases:
            errors.append(
                f"恢复图 {name} 的相邻正文缺少："
                + "、".join(f"‘{phrase}’" for phrase in missing_phrases)
            )
    return errors


def check_figure_outputs(root: Path) -> list[str]:
    """Return errors for missing or empty managed Word PNG and vector PDF files."""
    errors: list[str] = []
    output_locations = (
        (root / "outputs" / "word_figures", ".png"),
        (root / "figures" / "pgfplots" / "build", ".pdf"),
    )
    expected_paths = {
        directory / f"{basename}{suffix}"
        for directory, suffix in output_locations
        for basename in FIGURE_BASENAMES
    }
    for basename in FIGURE_BASENAMES:
        for directory, suffix in output_locations:
            path = directory / f"{basename}{suffix}"
            relative_path = path.relative_to(root)
            if not path.exists():
                errors.append(f"缺少图件输出：{relative_path}")
            elif not path.is_file():
                errors.append(f"图件输出不是普通文件：{relative_path}")
            elif path.stat().st_size == 0:
                errors.append(f"图件输出为空文件：{relative_path}")
    for directory, _suffix in output_locations:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.suffix.lower() in {".png", ".pdf"} and path not in expected_paths:
                errors.append(f"意外图件输出：{path.relative_to(root)}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Default: full rates, manuscript-theme, and figure-output checks."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Require exact rate equality instead of a 1 percentage-point tolerance; "
            "all full checks still run unless --rates-only is set."
        ),
    )
    parser.add_argument(
        "--rates-only",
        action="store_true",
        help=(
            "Run rates only (explicit diagnostic bypass); skip theme and "
            "figure-output checks."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root to check (default: inferred from this script).",
    )
    return parser


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, TypeError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_output()
    args = build_parser().parse_args(argv)
    root = args.root.resolve() if args.root is not None else Path(__file__).resolve().parents[2]
    manuscript_path = root / "docs" / "theory_and_simulation.md"
    csv_path = root / "outputs" / "ablation_study" / "ablation_summary.csv"
    tolerance = 0.0 if args.strict else 1.0

    try:
        paper_rates = parse_paper_rates(manuscript_path.read_text(encoding="utf-8"))
        csv_rates = read_csv_rates(csv_path)
    except (OSError, ValueError, KeyError) as error:
        print(f"{RED}FAIL: {error}{RESET}")
        return 1

    failed = False
    for variant in VARIANT_NAMES.values():
        if variant not in csv_rates:
            print(f"{RED}✗ {variant}: CSV 中缺少该变体{RESET}")
            failed = True
            continue
        paper_rate = paper_rates[variant]
        csv_rate = csv_rates[variant]
        difference = abs(paper_rate - csv_rate)
        message = (
            f"{variant}: paper={paper_rate:.1f}%, csv={csv_rate:.1f}% "
            f"(Δ={difference:.1f}%)"
        )
        if difference > tolerance:
            print(f"{RED}✗ {message}{RESET}")
            failed = True
        else:
            print(f"{GREEN}✓ {message}{RESET}")

    if not args.rates_only:
        for error in check_manuscript_theme(manuscript_path):
            print(f"{RED}✗ manuscript theme: {error}{RESET}")
            failed = True
        for error in check_manuscript_figures(manuscript_path):
            print(f"{RED}✗ manuscript figure: {error}{RESET}")
            failed = True
        for error in check_figure_outputs(root):
            print(f"{RED}✗ figure output: {error}{RESET}")
            failed = True

    if failed:
        print(f"{RED}FAIL{RESET}")
        return 1
    print(f"{GREEN}PASS{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
