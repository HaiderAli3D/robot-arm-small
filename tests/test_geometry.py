import math
import unittest

from arm_control.geometry import (
    Point, angle, associate_hands, clockwise_angle, pinch_ratio, signed_bend,
)


class GeometryTests(unittest.TestCase):
    def test_interior_angle_includes_depth(self):
        self.assertAlmostEqual(angle(Point(1, 0), Point(0, 0), Point(0, 0, 1)), 90)
        self.assertAlmostEqual(angle(Point(-1, 0), Point(0, 0), Point(1, 0)), 180)

    def test_degenerate_or_nonfinite_geometry_is_missing(self):
        self.assertIsNone(angle(Point(0, 0), Point(0, 0), Point(1, 0)))
        self.assertIsNone(angle(Point(math.nan, 0), Point(0, 0), Point(1, 0)))
        self.assertIsNone(clockwise_angle(0, 0))
        self.assertIsNone(signed_bend(0, 0, 1, 0))

    def test_screen_clockwise_and_signed_bend(self):
        self.assertAlmostEqual(clockwise_angle(0, 1), 90)
        self.assertAlmostEqual(signed_bend(1, 0, 0, 1), 90)
        self.assertAlmostEqual(signed_bend(0, 1, 1, 0), -90)
        self.assertAlmostEqual(signed_bend(-1, 0.01, -1, -0.01), 1.1458774)

    def test_pinch_is_scale_invariant_and_degenerate_is_missing(self):
        self.assertAlmostEqual(pinch_ratio(Point(0, 0), Point(0.5, 0), Point(0, 0), Point(1, 0)), 0.5)
        self.assertAlmostEqual(pinch_ratio(Point(0, 0), Point(5, 0), Point(0, 0), Point(10, 0)), 0.5)
        self.assertIsNone(pinch_ratio(Point(0, 0), Point(1, 0), Point(0, 0), Point(0, 0)))

    def test_association_uses_proximity_not_detection_order(self):
        wrists = {"left": Point(0.2, 0.3), "right": Point(0.8, 0.3)}
        hands = [Point(0.79, 0.3), Point(0.21, 0.3)]
        self.assertEqual(associate_hands(wrists, hands, 0.1, 0.02), {"left": 1, "right": 0})

    def test_association_omits_far_and_ambiguous_hands(self):
        self.assertEqual(associate_hands({"left": Point(0, 0)}, [Point(0.5, 0)], 0.1, 0.02), {})
        self.assertEqual(associate_hands({"left": Point(0, 0)}, [Point(0.01, 0), Point(-0.01, 0)], 0.1, 0.02), {})
        self.assertEqual(associate_hands({"left": Point(0, 0), "right": Point(0.02, 0)}, [Point(0.01, 0)], 0.1, 0.02), {})

    def test_one_hand_is_never_assigned_to_two_arms(self):
        result = associate_hands({"left": Point(0, 0), "right": Point(0.08, 0)}, [Point(0.01, 0)], 0.1, 0.02)
        self.assertEqual(result, {"left": 0})


if __name__ == "__main__":
    unittest.main()
