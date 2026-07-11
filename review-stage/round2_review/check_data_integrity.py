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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Require exact equality instead of allowing a 1 percentage-point tolerance.",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
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

    if failed:
        print(f"{RED}FAIL{RESET}")
        return 1
    print(f"{GREEN}PASS{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
