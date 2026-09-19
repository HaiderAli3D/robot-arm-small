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

    def test_project_claw_gain_is_twenty_times_lower_and_returns_to_zero(self):
        config = load_config(Path(__file__).resolve().parents[1] / 'config.toml')
        c = calibrated(replace(config,smoothing_tau=0,deadband=0))
        self.assertAlmostEqual(c.update(Observation(0,0,0,.92),1.15)[3],45)
        self.assertAlmostEqual(c.update(Observation(0,0,0,.96),1.2)[3],67.5)
        self.assertAlmostEqual(c.update(Observation(0,0,0,.6),1.3)[3],-135)
        self.assertEqual(c.update(Observation(0,0,0,.2),1.4)[3],-360)
        self.assertEqual(c.update(Observation(0,0,0,1),1.5)[3],90)

    def test_project_left_rotation_moves_four_degrees_per_input_degree(self):
        config = load_config(Path(__file__).resolve().parents[1] / 'config.toml')
        c = calibrated(replace(config,smoothing_tau=0,deadband=0))
        self.assertEqual(c.update(Observation(5,0,0,1),1.2), (110,90,90,90))
        self.assertEqual(c.update(Observation(-5,0,0,1),1.3), (70,90,90,90))
        self.assertEqual(c.update(NEUTRAL,1.4), (90,)*4)

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

    def test_pinched_calibration_preserves_claw_then_tracks_relative_change(self):
        for ratio in (0,.2,.20000001,.4):
            c = calibrated(observation=Observation(0,90,60,ratio))
            self.assertEqual(advance(c,Observation(0,90,60,ratio))[3],90)
            reference_closure = max(0,min(1,(1-ratio)/.8))
            closed = advance(c,Observation(0,90,60,.2),start=3.1)
            self.assertAlmostEqual(closed[3],90-90*(1-reference_closure))
            opened = advance(c,Observation(0,90,60,1),start=5.1)
            self.assertAlmostEqual(opened[3],90+90*reference_closure)
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

    def test_calibration_zeros_current_servo_pose_without_moving_any_joint(self):
        for running in (False,True):
            with self.subTest(running=running):
                c = Controller(Config(smoothing_tau=0,deadband=0))
                held = (130,-45,230,35)
                c.sync_angles(held)
                if running: c.resume(0,capture_reference=False)
                c.begin_calibration(0,delay=4)
                pose = Observation(20,80,-25,.6)
                c.update(pose,3.9)
                self.assertEqual(c.positions,(40,-135,140,-55))
                self.assertEqual(c.update(pose,4),held)
                self.assertEqual(c.zero_angles,held)
                self.assertEqual(c.positions,(0,0,0,0))
                self.assertEqual(c.active,running)
                c.resume(4)
                self.assertEqual(c.update(pose,4.1),held)
                moved = c.update(Observation(30,90,-35,.8),4.2)
                for actual,expected in zip(moved,(140,-35,220,57.5)):
                    self.assertAlmostEqual(actual,expected)
                self.assertEqual(c.update(pose,4.3),held)

    def test_recalibration_uses_latest_position_without_accumulating_old_zero(self):
        c = calibrated()
        c.update(Observation(20,30,40,.6),1.2)
        held = c.angles
        c.begin_calibration(2)
        pose = Observation(-10,60,25,.4)
        c.update(pose,2)
        self.assertEqual(c.zero_angles,held)
        self.assertEqual(c.positions,(0,0,0,0))
        self.assertEqual(c.update(pose,2.1),held)
        c.sync_angles((110,140,160,25))
        self.assertEqual(c.zero_angles,held)
        c.begin_calibration(3)
        c.update(pose,3)
        self.assertEqual(c.zero_angles,(110,140,160,25))
        self.assertEqual(c.positions,(0,0,0,0))

    def test_project_elbow_and_wrist_are_four_times_more_sensitive(self):
        config = load_config(Path(__file__).resolve().parents[1]/'config.toml')
        c = calibrated(replace(config,smoothing_tau=0,deadband=0),Observation(0,45,0,1))
        self.assertEqual(c.update(Observation(0,50,0,1),1.2),(90,110,90,90))
        self.assertEqual(c.update(Observation(0,45,-5,1),1.3),(90,90,70,90))

    def test_unencodable_tracking_keeps_channel_valid_and_running(self):
        for edge,step in ((2**31-1,1),(-(2**31),-1)):
            with self.subTest(edge=edge):
                c = Controller(Config(smoothing_tau=0,deadband=0))
                c.sync_angles((90,edge,90,90))
                c.begin_calibration(0)
                c.update(Observation(0,90,0,1),0)
                c.resume(0)
                c.update(Observation(5,90+step,0,1),.1)
                self.assertEqual(c.angles,(95,edge,90,90))
                self.assertIn('IO7',c.status)
                self.assertIn('integer',c.status)
                self.assertTrue(c.active)
                c.update(Observation(0,90-step,0,1),.2)
                self.assertEqual(c.angles,(90,edge-step,90,90))
                self.assertNotIn('integer',c.status)

    def test_relative_pinch_encoding_overflow_never_corrupts_output(self):
        c = Controller(Config(claw_closed=-(2**31),smoothing_tau=0,deadband=0))
        c.begin_calibration(0)
        c.update(Observation(0,0,0,.2),0)
        c.resume(0)
        c.update(Observation(0,0,0,1),.1)
        self.assertEqual(c.angles,(90,)*4)
        self.assertIn('IO9',c.status)
        self.assertTrue(c.active)


if __name__ == "__main__":
    unittest.main()
