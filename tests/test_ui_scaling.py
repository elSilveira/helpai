import unittest

from ui_scaling import calculate_scale, scale_px


class UiScalingTests(unittest.TestCase):
    def test_calculate_scale_uses_96_dpi_as_baseline(self):
        self.assertEqual(1.0, calculate_scale(96))
        self.assertEqual(2.0, calculate_scale(192))

    def test_calculate_scale_clamps_extreme_values(self):
        self.assertEqual(1.0, calculate_scale(72))
        self.assertEqual(2.5, calculate_scale(384))

    def test_scale_px_rounds_and_never_returns_zero_for_positive_values(self):
        self.assertEqual(15, scale_px(10, 1.5))
        self.assertEqual(1, scale_px(1, 0.25))
        self.assertEqual(0, scale_px(0, 2.0))


if __name__ == "__main__":
    unittest.main()
