import unittest

from app import crossing_within_segment, percentile, stable_side


class GeometryTests(unittest.TestCase):
    def test_hysteresis_and_crossing_limits(self) -> None:
        start = (0.2, 0.5)
        end = (0.8, 0.5)
        self.assertEqual(stable_side((0.5, 0.505), start, end, 0.01), 0)
        self.assertEqual(stable_side((0.5, 0.6), start, end, 0.01), 1)
        self.assertTrue(crossing_within_segment((0.5, 0.4), (0.5, 0.6), start, end))
        self.assertFalse(crossing_within_segment((0.9, 0.4), (0.9, 0.6), start, end))

    def test_percentile_uses_linear_interpolation(self) -> None:
        self.assertEqual(percentile([1.0, 2.0, 3.0], 0.5), 2.0)


if __name__ == "__main__":
    unittest.main()
