import math
import unittest

from arm_control.arm_stage import (
    BASE_LINK_LENGTH, FOREARM_LINK_LENGTH, TOOL_LINK_LENGTH, arm_geometry,
)


class ArmGeometryTests(unittest.TestCase):
    def test_short_base_and_extended_tool_keep_their_lengths(self):
        self.assertLess(BASE_LINK_LENGTH, 151 / 2)
        self.assertGreater(TOOL_LINK_LENGTH, 59 * 2)
        for elbow in (0, 45, 90, 135, 180):
            pose = arm_geometry((90, elbow, 90, 90))
            for start, end, length in (
                ('shoulder', 'joint', BASE_LINK_LENGTH),
                ('joint', 'end', FOREARM_LINK_LENGTH),
                ('end', 'hand_end', TOOL_LINK_LENGTH),
            ):
                self.assertAlmostEqual(math.dist(pose[start], pose[end]), length)

    def test_elbow_moves_half_as_far_in_the_reversed_direction(self):
        poses = [arm_geometry((90, elbow, 90, 90)) for elbow in (0, 45, 90, 135, 180)]
        angles = [pose['arm_angle'] for pose in poses]
        self.assertAlmostEqual(angles[-1] - angles[0], -math.pi / 2)
        for before, after in zip(angles, angles[1:]):
            self.assertAlmostEqual(after - before, -math.pi / 8)
        # Both ends of the sweep reach opposite sides of the same pivot.
        left, right = poses[0], poses[-1]
        self.assertGreater(left['end'][0], left['joint'][0])
        self.assertLess(right['end'][0], right['joint'][0])
        self.assertLess(poses[2]['end'][1], poses[2]['joint'][1])
        self.assertAlmostEqual(angles[2], -math.pi / 2)

    def test_halving_visual_response_keeps_full_sweep_available(self):
        start = arm_geometry((90, -90, 90, 90))
        finish = arm_geometry((90, 270, 90, 90))
        self.assertAlmostEqual(finish['arm_angle'] - start['arm_angle'], -math.pi)
        # Scale before wrapping: crossing raw 360 must not jump by half a turn.
        before = arm_geometry((90, 359, 90, 90))
        after = arm_geometry((90, 361, 90, 90))
        self.assertAlmostEqual(after['arm_angle'] - before['arm_angle'], -math.radians(1))

    def test_full_range_and_extreme_commands_remain_finite(self):
        for angle in (-(2**31), -270, -90, 0, 90, 180, 270, 2**31 - 1):
            commands = (angle,) * 4
            pose = arm_geometry(commands)
            for point in ('shoulder', 'joint', 'end', 'hand_end'):
                self.assertTrue(all(math.isfinite(value) for value in pose[point]))
            self.assertEqual(commands, (angle,) * 4)
