import math
import unittest

from arm_control.config import Config, JointConfig
from arm_control.control import Controller, Observation


NEUTRAL = Observation(0, 0, 0, 1)


def calibrated(config=None, observation=NEUTRAL):
    controller = Controller(config or Config(smoothing_tau=0, deadband=0))
    controller.begin_calibration(0)
    for tick in range(12):
        controller.update(observation, tick / 10)
    assert controller.calibrated
    assert controller.resume(1.1)
    return controller


def advance(controller, observation, start=1.1, frames=20):
    for tick in range(1, frames + 1):
        controller.update(observation, start + tick / 10)
    return controller.angles


class ControllerTests(unittest.TestCase):
    def test_requires_calibration_and_explicit_resume(self):
        c = Controller(Config())
        self.assertFalse(c.resume(0))
        c.begin_calibration(0)
        for tick in range(11):
            c.update(NEUTRAL, tick / 10)
        self.assertTrue(c.calibrated)
        self.assertFalse(c.active)
        self.assertEqual(c.angles, (90, 90, 90, 90))
        self.assertTrue(c.resume(1))

    def test_neutral_relative_mapping_and_proportional_pinch(self):
        c = calibrated(observation=Observation(30, 5, -5, 1))
        actual = advance(c, Observation(60, 50, -35, 0.6))
        for got, expected in zip(actual, (120, 135, 60, 45)):
            self.assertAlmostEqual(got, expected)
        self.assertEqual(advance(c, Observation(30, 5, -5, 1), start=3.1), (90, 90, 90, 90))

    def test_joint_reversal_gain_and_bounds_include_claw(self):
        joints = (JointConfig(70, 110, -1, 2), JointConfig(0, 110, 1, 2),
                  JointConfig(60, 130, -1, 1), JointConfig(0, 120, -1, 0.5))
        c = calibrated(Config(joints=joints, smoothing_tau=0, deadband=0))
        self.assertEqual(advance(c, Observation(30, 30, -50, 0.2)), (70, 110, 130, 120))

    def test_rotation_wrap_and_repeated_pose_does_not_accumulate(self):
        c = calibrated(observation=Observation(179, 0, 0, 1))
        self.assertAlmostEqual(advance(c, Observation(-179, 0, 0, 1))[0], 92)
        self.assertAlmostEqual(advance(c, Observation(-179, 0, 0, 1), start=3.1)[0], 92)

    def test_calibration_uses_circular_reference(self):
        c = Controller(Config(smoothing_tau=0, deadband=0))
        c.begin_calibration(0)
        for tick in range(11):
            c.update(Observation(179 if tick % 2 else -179, 0, 0, 1), tick / 10)
        self.assertTrue(c.resume(1))
        self.assertLess(abs(advance(c, Observation(180, 0, 0, 1), start=1)[0] - 90), 0.2)

    def test_calibration_requires_stable_straight_open_pose(self):
        for invalid in (Observation(0, 30, 0, 1), Observation(0, 0, 30, 1),
                        Observation(0, 0, 0, 0.4), Observation(None, 0, 0, 1)):
            c = Controller(Config())
            c.begin_calibration(0)
            for tick in range(15):
                c.update(invalid, tick / 10)
            self.assertFalse(c.calibrated)
        c = Controller(Config())
        c.begin_calibration(0)
        for tick in range(15):
            c.update(Observation(tick * 5, 0, 0, 1), tick / 10)
        self.assertFalse(c.calibrated)
        for tick in range(15, 26):
            c.update(Observation(75, 0, 0, 1), tick / 10)
        self.assertTrue(c.calibrated)

    def test_calibration_tracking_gap_restarts_stability_period(self):
        c = Controller(Config())
        c.begin_calibration(0)
        c.update(NEUTRAL, 0)
        c.update(NEUTRAL, 2)
        self.assertFalse(c.calibrated)

    def test_calibration_explains_each_rejected_measurement(self):
        cases = (
            (Observation(None,0,0,1), 'left hand'),
            (Observation(0,None,0,1), 'right shoulder'),
            (Observation(0,0,None,1), 'right wrist'),
            (Observation(0,0,0,None), 'right palm'),
            (Observation(0,35,0,1), '35'),
            (Observation(0,0,-30,1), '30'),
            (Observation(0,0,0,.3), 'thumb and index'),
        )
        for observation, explanation in cases:
            with self.subTest(observation=observation):
                c = Controller(Config())
                c.begin_calibration(0)
                c.update(observation, 0)
                self.assertIn(explanation, c.status)
                self.assertFalse(c.calibrated)

    def test_calibration_reports_progress_and_reason_for_restart(self):
        c = Controller(Config())
        c.begin_calibration(0)
        for tick in range(6):
            c.update(NEUTRAL, tick / 10)
        self.assertIn('50%', c.status)
        c.update(Observation(25,0,0,1), .6)
        self.assertIn('left hand moved', c.status)
        self.assertIn('0%', c.status)

    def test_slew_rate_and_smoothing(self):
        c = calibrated(Config(smoothing_tau=0, deadband=0, max_speed=30))
        self.assertAlmostEqual(c.update(Observation(90, 90, 90, 0.2), 1.2)[0], 93)
        smooth = calibrated(Config(smoothing_tau=1, deadband=0, max_speed=90))
        delta = smooth.update(Observation(10, 0, 0, 1), 1.2)[0] - 90
        self.assertGreater(delta, 0)
        self.assertLess(delta, 1)

    def test_deadband_ignores_jitter(self):
        c = calibrated(Config(smoothing_tau=0, deadband=1))
        self.assertEqual(advance(c, Observation(0.5, 0.5, -0.5, 1)), (90, 90, 90, 90))

    def test_missing_joint_freezes_only_affected_output(self):
        c = calibrated()
        c.update(Observation(30, None, 30, None), 1.2)
        self.assertGreater(c.angles[0], 90)
        self.assertEqual(c.angles[1], 90)
        self.assertGreater(c.angles[2], 90)
        self.assertEqual(c.angles[3], 90)
        self.assertTrue(c.active)

    def test_prolonged_loss_pauses_all_and_reacquisition_requires_resume(self):
        c = calibrated()
        for tick in range(6):
            c.update(Observation(30, None, 30, 1), 1.2 + tick / 10)
        self.assertFalse(c.active)
        held = c.angles
        self.assertFalse(c.resume(1.7))
        c.update(Observation(90, 90, 90, 0.2), 1.8)
        self.assertEqual(c.angles, held)
        self.assertFalse(c.active)
        self.assertTrue(c.resume(1.8))

    def test_different_missing_channels_still_count_as_continuous_loss(self):
        c = calibrated()
        for tick in range(7):
            c.update(Observation(None, 0, 0, 1) if tick % 2 else Observation(0, None, 0, 1), 1.2 + tick / 10)
        self.assertFalse(c.active)

    def test_long_frame_gap_pauses_before_new_movement(self):
        c = calibrated()
        self.assertEqual(c.update(Observation(90, 90, 90, 0.2), 2), (90, 90, 90, 90))
        self.assertFalse(c.active)
        self.assertTrue(c.resume(2))

    def test_resume_rejects_stale_observation(self):
        c = calibrated()
        c.pause()
        self.assertFalse(c.resume(1.7))
        self.assertFalse(c.active)

    def test_pause_does_not_accumulate_smoothing_state(self):
        c = calibrated(Config(smoothing_tau=1, deadband=0))
        c.pause()
        advance(c, Observation(90, 90, 90, 0.2))
        c.update(NEUTRAL, 3.2)
        self.assertTrue(c.resume(3.2))
        self.assertEqual(c.update(NEUTRAL, 3.3), (90, 90, 90, 90))

    def test_nan_negative_pinch_and_invalid_elbow_are_missing(self):
        for obs in (Observation(math.nan, 0, 0, 1), Observation(0, -1, 0, 1),
                    Observation(0, 181, 0, 1), Observation(0, 0, 0, -0.1)):
            c = calibrated()
            for tick in range(7):
                c.update(obs, 1.2 + tick / 10)
            self.assertFalse(c.active)
            self.assertTrue(all(math.isfinite(v) for v in c.angles))

    def test_reset_cancels_in_progress_calibration(self):
        c = calibrated()
        c.begin_calibration(1.2)
        c.reset((85, 95, 90, 90))
        advance(c, NEUTRAL, start=1.2)
        self.assertFalse(c.calibrated)
        self.assertFalse(c.active)
        self.assertEqual(c.angles, (85, 95, 90, 90))

    def test_sync_held_angles_preserves_calibration_and_clears_filter(self):
        c = calibrated(Config(smoothing_tau=1, deadband=0))
        c.update(Observation(90, 90, 90, 0.2), 1.2)
        c.pause()
        c.sync_angles((85, 95, 90, 90))
        self.assertTrue(c.calibrated)
        self.assertFalse(c.active)
        self.assertEqual(c.angles, (85, 95, 90, 90))
        c.update(Observation(-5, 5, 0, 1), 1.3)
        self.assertTrue(c.resume(1.3))
        self.assertEqual(c.update(Observation(-5, 5, 0, 1), 1.4), (85, 95, 90, 90))

    def test_sync_rejects_active_state_and_invalid_angles(self):
        c = calibrated()
        with self.assertRaises(ValueError):
            c.sync_angles((90, 90, 90, 90))
        c.pause()
        for angles in ((90, 90), (90, 90, 90, math.nan), (90, 90, 90, 181)):
            with self.assertRaises(ValueError):
                c.sync_angles(angles)
        self.assertEqual(c.angles, (90, 90, 90, 90))

    def test_reacquisition_at_loss_deadline_cannot_bypass_pause(self):
        c = calibrated()
        for now in (1.2, 1.4, 1.6):
            c.update(Observation(0, None, 0, 1), now)
        self.assertEqual(c.update(Observation(90, 90, 90, 0.2), 1.7), (90, 90, 90, 90))
        self.assertFalse(c.active)


if __name__ == "__main__":
    unittest.main()
