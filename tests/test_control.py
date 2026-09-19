import math
import unittest
from dataclasses import replace
from pathlib import Path

from arm_control.config import Config, JointConfig, load_config
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
    def test_resume_starts_without_calibration_and_captures_when_visible(self):
        c = Controller(Config())
        self.assertTrue(c.resume(0))
        c.update(Observation(None,None,None,None),10)
        self.assertTrue(c.active)
        self.assertFalse(c.calibrated)
        c.update(NEUTRAL,11)
        self.assertTrue(c.calibrated)
        self.assertTrue(c.active)
        self.assertEqual(c.angles, (90, 90, 90, 90))

    def test_neutral_relative_mapping_and_proportional_pinch(self):
        c = calibrated(observation=Observation(30, 5, -5, 1))
        actual = advance(c, Observation(60, 50, -35, 0.6))
        for got, expected in zip(actual, (120, 135, 60, 45)):
            self.assertAlmostEqual(got, expected)
        self.assertEqual(advance(c, Observation(30, 5, -5, 1), start=3.1), (90, 90, 90, 90))

    def test_joint_reversal_and_gain_without_output_clipping(self):
        joints = (JointConfig(direction=-1, gain=2), JointConfig(gain=2),
                  JointConfig(direction=-1), JointConfig(direction=-1, gain=0.5))
        c = calibrated(Config(joints=joints, smoothing_tau=0, deadband=0))
        self.assertEqual(advance(c, Observation(30, 30, -50, 0.2)), (30, 150, 140, 135))

    def test_elbow_only_drives_gpio7_and_wrist_only_drives_gpio8(self):
        c = calibrated(observation=Observation(0,30,10,1))
        self.assertEqual(c.update(Observation(0,60,10,1),1.2),(90,120,90,90))
        self.assertEqual(c.update(Observation(0,30,-20,1),1.3),(90,90,60,90))

    def test_project_claw_gain_doubles_response_and_reaches_both_endpoints(self):
        config = load_config(Path(__file__).resolve().parents[1] / 'config.toml')
        c = calibrated(replace(config,smoothing_tau=0,deadband=0))
        self.assertAlmostEqual(c.update(Observation(0,0,0,.8),1.2)[3],45)
        self.assertAlmostEqual(c.update(Observation(0,0,0,.6),1.3)[3],0)
        self.assertEqual(c.update(Observation(0,0,0,.2),1.4)[3],-90)
        self.assertEqual(c.update(Observation(0,0,0,1),1.5)[3],90)

    def test_rotation_wrap_and_repeated_pose_does_not_accumulate(self):
        c = calibrated(observation=Observation(179, 0, 0, 1))
        self.assertAlmostEqual(advance(c, Observation(-179, 0, 0, 1))[0], 92)
        self.assertAlmostEqual(advance(c, Observation(-179, 0, 0, 1), start=3.1)[0], 92)

    def test_snapshot_reference_preserves_rotation_wraparound(self):
        c = Controller(Config(smoothing_tau=0, deadband=0))
        c.begin_calibration(0)
        c.update(Observation(179,0,0,1), 0)
        self.assertTrue(c.resume(0))
        self.assertAlmostEqual(advance(c, Observation(-179,0,0,1), start=0)[0], 92)

    def test_calibration_accepts_any_detected_pose_in_one_frame(self):
        for pose in (Observation(100,90,-65,1), Observation(-140,150,100,.4),
                     Observation(0,180,-180,.2), Observation(0,0,0,0)):
            c = Controller(Config())
            c.begin_calibration(0)
            self.assertEqual(c.update(pose,0), (90,)*4)
            self.assertTrue(c.calibrated)
            self.assertFalse(c.active)
            self.assertTrue(c.resume(0))
            self.assertEqual(c.update(pose,.1)[:3], (90,)*3)

    def test_calibration_waits_only_for_missing_tracking(self):
        c = Controller(Config())
        c.begin_calibration(0,delay=4)
        c.update(Observation(None,90,50,0), 4)
        self.assertFalse(c.calibrated)
        c.update(Observation(80,90,50,0), 4.1)
        self.assertTrue(c.calibrated)

    def test_calibration_explains_each_rejected_measurement(self):
        cases = (
            (Observation(None,0,0,1), 'left hand'),
            (Observation(0,None,0,1), 'right shoulder'),
            (Observation(0,0,None,1), 'right wrist'),
            (Observation(0,0,0,None), 'right palm'),
        )
        for observation, explanation in cases:
            with self.subTest(observation=observation):
                c = Controller(Config())
                c.begin_calibration(0)
                c.update(observation, 0)
                self.assertIn(explanation, c.status)
                self.assertFalse(c.calibrated)

    def test_pinched_calibration_never_divides_by_zero_and_claw_still_opens(self):
        for ratio in (0,.2,.20000001,.4):
            c = calibrated(observation=Observation(0,90,60,ratio))
            closed = advance(c,Observation(0,90,60,.2))
            self.assertAlmostEqual(closed[3],0)
            opened = advance(c,Observation(0,90,60,1),start=3.1)
            self.assertAlmostEqual(opened[3],90)
            self.assertTrue(all(math.isfinite(v) for v in opened))

    def test_no_slew_cap_and_optional_smoothing(self):
        c = calibrated(Config(smoothing_tau=0, deadband=0))
        self.assertEqual(c.update(Observation(90, 90, 90, 0.2), 1.2), (180,180,180,0))
        smooth = calibrated(Config(smoothing_tau=1, deadband=0))
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
        self.assertGreater(c.angles[2], 90)
        self.assertEqual(c.angles[1], 90)
        self.assertEqual(c.angles[3], 90)
        self.assertTrue(c.active)

    def test_prolonged_loss_stays_running_and_reacquisition_moves_immediately(self):
        c = calibrated()
        for tick in range(6):
            c.update(Observation(30, None, 30, 1), 1.2 + tick / 10)
        self.assertTrue(c.active)
        held = c.angles
        c.update(Observation(None,None,None,None), 600)
        self.assertEqual(c.angles,held)
        self.assertTrue(c.active)
        c.update(Observation(90, 90, 90, 0.2), 600.1)
        self.assertEqual(c.angles,(180,180,180,0))
        self.assertTrue(c.active)

    def test_different_missing_channels_do_not_pause(self):
        c = calibrated()
        for tick in range(7):
            c.update(Observation(None, 0, 0, 1) if tick % 2 else Observation(0, None, 0, 1), 1.2 + tick / 10)
        self.assertTrue(c.active)

    def test_long_frame_gap_does_not_pause(self):
        c = calibrated()
        self.assertEqual(c.update(Observation(90, 90, 90, 0.2), 20), (180,180,180,0))
        self.assertTrue(c.active)

    def test_resume_accepts_stale_or_missing_observation(self):
        c = calibrated()
        c.pause()
        self.assertTrue(c.resume(1.7))
        self.assertTrue(c.active)

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
            self.assertTrue(c.active)
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

    def test_sync_preserves_run_state_and_rejects_unencodable_angles(self):
        c = calibrated()
        c.sync_angles((90,90,90,90))
        self.assertTrue(c.active)
        for angles in ((90, 90), (90, 90, 90, math.nan), (90, 90, 90, 2**31)):
            with self.assertRaises(ValueError):
                c.sync_angles(angles)
        self.assertEqual(c.angles, (90, 90, 90, 90))

    def test_explicit_pause_stays_paused_through_reacquisition(self):
        c = calibrated()
        c.pause()
        for now in (1.2, 1.4, 1.6):
            c.update(Observation(0, None, 0, 1), now)
        self.assertEqual(c.update(Observation(90, 90, 90, 0.2), 1.7), (90, 90, 90, 90))
        self.assertFalse(c.active)

    def test_recalibration_retains_running_state_and_manual_pause_still_works(self):
        c = calibrated()
        c.begin_calibration(2,delay=4)
        self.assertTrue(c.active)
        for now in (3,4,5):
            self.assertEqual(c.update(Observation(50,80,40,.3),now),(90,)*4)
            self.assertTrue(c.active)
        c.update(Observation(50,80,40,.3),6)
        self.assertTrue(c.active)
        self.assertTrue(c.calibrated)
        c.pause()
        c.update(Observation(90,90,90,.1),7)
        self.assertFalse(c.active)
        self.assertEqual(c.angles,(90,)*4)

    def test_tracking_crosses_old_limits_on_every_channel(self):
        c = calibrated(Config(smoothing_tau=0, deadband=0,
                              joints=(JointConfig(gain=2),) * 4))
        self.assertEqual(c.update(Observation(100,100,-100,.2),1.2),
                         (290,290,-110,-90))
        self.assertEqual(c.positions,(200,200,-200,-180))
        self.assertTrue(c.active)

    def test_keyboard_can_cross_both_old_endpoints_and_reverse_immediately(self):
        for index in range(4):
            c = Controller(Config())
            c.nudge(index,180)
            self.assertEqual(c.positions[index],180)
            c.nudge(index,-5)
            self.assertEqual(c.positions[index],175)
            c.nudge(index,-355)
            self.assertEqual(c.positions[index],-180)
            c.nudge(index,5)
            self.assertEqual(c.positions[index],-175)

    def test_sync_accepts_extended_device_positions(self):
        c = Controller(Config())
        c.sync_angles((-270,-90,270,450))
        self.assertEqual(c.positions,(-360,-180,180,360))


if __name__ == "__main__":
    unittest.main()
