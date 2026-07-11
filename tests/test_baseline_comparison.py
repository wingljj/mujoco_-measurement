import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from baseline_comparison import ABLATION_VARIANTS


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


if __name__ == "__main__":
    unittest.main()
