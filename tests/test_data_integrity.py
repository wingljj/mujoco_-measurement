import sys
import os
import subprocess
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

from check_data_integrity import parse_paper_rates


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
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=False,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode("gbk", errors="replace"))


if __name__ == "__main__":
    unittest.main()
