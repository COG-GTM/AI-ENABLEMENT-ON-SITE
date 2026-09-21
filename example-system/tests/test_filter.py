"""SN-REQ-003 - 4-sample moving average."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))

from sensor_node.filter import MovingAverage  # noqa: E402


class TestMovingAverage(unittest.TestCase):
    def test_warm_up_averages_available_samples(self):
        f = MovingAverage(4)
        self.assertEqual(f.update(100), 100)
        self.assertEqual(f.update(200), 150)
        self.assertEqual(f.update(300), 200)
        self.assertEqual(f.update(400), 250)

    def test_window_slides(self):
        f = MovingAverage(4)
        for v in (100, 200, 300, 400):
            f.update(v)
        self.assertEqual(f.update(800), (200 + 300 + 400 + 800) // 4)

    def test_negative_truncates_toward_zero_like_c(self):
        f = MovingAverage(4)
        f.update(-1)
        f.update(-1)
        self.assertEqual(f.update(-1), -1)
        self.assertEqual(f.update(0), 0)  # -3 / 4 -> 0 in C, not -1

    def test_reset(self):
        f = MovingAverage(4)
        f.update(1000)
        f.reset()
        self.assertEqual(f.count, 0)
        self.assertEqual(f.update(10), 10)

    def test_invalid_window(self):
        with self.assertRaises(ValueError):
            MovingAverage(0)


if __name__ == "__main__":
    unittest.main()
