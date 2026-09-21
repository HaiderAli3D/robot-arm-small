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

    def test_elbow_covers_a_linear_reversed_half_turn(self):
        poses = [arm_geometry((90, elbow, 90, 90)) for elbow in (0, 45, 90, 135, 180)]
        angles = [pose['arm_angle'] for pose in poses]
        self.assertAlmostEqual(angles[-1] - angles[0], -math.pi)
        for before, after in zip(angles, angles[1:]):
            self.assertAlmostEqual(after - before, -math.pi / 4)
        # Both ends of the sweep reach opposite sides of the same pivot.
        left, right = poses[0], poses[-1]
        self.assertGreater(left['end'][0], left['joint'][0])
        self.assertLess(right['end'][0], right['joint'][0])
        self.assertLess(poses[2]['end'][1], poses[2]['joint'][1])

    def test_full_range_and_extreme_commands_remain_finite(self):
        for angle in (-(2**31), -270, -90, 0, 90, 180, 270, 2**31 - 1):
            commands = (angle,) * 4
            pose = arm_geometry(commands)
            for point in ('shoulder', 'joint', 'end', 'hand_end'):
                self.assertTrue(all(math.isfinite(value) for value in pose[point]))
            self.assertEqual(commands, (angle,) * 4)
