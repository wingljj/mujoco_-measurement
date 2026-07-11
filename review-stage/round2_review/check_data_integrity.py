"""Check that the manuscript's default ablation rates match the source CSV."""

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
LEGACY_THEME_TERMS = ("持杯", "杯体", "防洒", "倾洒", "液体晃动", "容器运输")
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


def check_manuscript_theme(path_or_text: Path | str) -> list[str]:
    """Return manuscript-theme errors, including line numbers for legacy terms."""
    manuscript = _read_path_or_text(path_or_text)
    errors: list[str] = []

    for line_number, line in enumerate(manuscript.splitlines(), start=1):
        for term in LEGACY_THEME_TERMS:
            if term in line:
                errors.append(f"第 {line_number} 行包含旧主题词‘{term}’。")

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
    if "10°" not in manuscript:
        errors.append("正文缺少 10° 报告阈值。")
    if "保守运输" not in manuscript:
        errors.append("正文缺少‘保守运输’阈值定性。")

    calibration_boundary = re.search(
        r"(?:未执行|未进行|未包含|未采用|未做|没有执行|没有进行|"
        r"没有包含|没有采用|不包含)[^。；\n]{0,50}(?:真实|实物)?"
        r"[^。；\n]{0,10}标定",
        manuscript,
    )
    measurement_mapping_boundary = re.search(
        r"(?:未建立|未包含|没有建立|没有包含|不包含)[^。；\n]{0,100}"
        r"(?:测量结果[^。；\n]{0,30}(?:映射|误差模型)|测量映射|"
        r"倾角[^。；\n]{0,50}(?:映射|误差模型))",
        manuscript,
    )
    if calibration_boundary is None:
        errors.append("正文缺少‘未做真实标定’的研究边界。")
    if measurement_mapping_boundary is None:
        errors.append("正文缺少‘未建立运输倾角到测量结果映射’的研究边界。")

    return errors


def check_figure_outputs(root: Path) -> list[str]:
    """Return errors for missing or empty managed Word PNG and vector PDF files."""
    errors: list[str] = []
    expected_basenames = set(FIGURE_BASENAMES)
    output_locations = (
        (root / "outputs" / "word_figures", ".png"),
        (root / "figures" / "pgfplots" / "build", ".pdf"),
    )
    for basename in FIGURE_BASENAMES:
        for directory, suffix in output_locations:
            path = directory / f"{basename}{suffix}"
            relative_path = path.relative_to(root)
            if not path.exists():
                errors.append(f"缺少图件输出：{relative_path}")
            elif not path.is_file() or path.stat().st_size == 0:
                errors.append(f"图件输出为空文件：{relative_path}")
    for directory, suffix in output_locations:
        for path in directory.glob(f"fig*{suffix}"):
            if path.stem not in expected_basenames:
                errors.append(f"意外图件输出：{path.relative_to(root)}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require exact equality instead of allowing a 1 percentage-point tolerance.",
    )
    parser.add_argument(
        "--rates-only",
        action="store_true",
        help="Check manuscript/CSV rates only; skip manuscript-theme and figure-output checks.",
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
    root = Path(__file__).resolve().parents[2]
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
