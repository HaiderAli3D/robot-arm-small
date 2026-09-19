import unittest

from arm_control.config import Config, JointConfig
from arm_control.control import Observation
from arm_control.session import Session
from arm_control.transport import LinkError


NEUTRAL = Observation(-90, 0, 0, 1)


class Device:
    def __init__(self):
        self.commands = []
        self.fail = False
        self.connect_angles = (90,)*4
        self.connect_error = None
        self.resume_error = None

    def connect(self):
        self.commands.append('hello')
        if self.connect_error:
            raise self.connect_error
        return self.connect_angles

    def resume(self):
        self.commands.append('resume')
        if self.resume_error:
            raise self.resume_error

    def hold(self):
        self.commands.append('hold')
        return (91, 92, 93, 94)

    def off(self):
        self.commands.append('off')
        if self.fail:
            raise LinkError('USB unplugged')

    def send_pose(self, angles):
        if self.fail:
            raise LinkError('USB unplugged')
        self.commands.append(tuple(angles))

    def close(self):
        self.commands.append('close')


class SessionTests(unittest.TestCase):
    def prepare(self, device=None):
        session = Session(Config(), device)
        if device:
            session.connect()
        session.calibrate(-4)
        for i in range(12):
            session.step(NEUTRAL, i*.1)
        return session

    def test_calibration_waits_four_seconds_before_collecting_pose(self):
        device = Device()
        session = Session(Config(), device)
        session.connect()
        session.calibrate(0)
        self.assertIn('4 seconds', session.controller.status)
        for tick in range(40):
            session.step(NEUTRAL, tick / 10)
        self.assertFalse(session.controller.calibrated)
        self.assertIn('1 seconds', session.controller.status)
        session.step(Observation(-45,90,60,.2), 4.0)
        self.assertTrue(session.controller.calibrated)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands, ['hello', 'off', 'resume', (90,)*4])

    def test_countdown_survives_missing_hands_and_restarts_on_c(self):
        session = Session(Config())
        session.calibrate(0)
        session.step(Observation(None,None,None,None), 2)
        self.assertIn('2 seconds', session.controller.status)
        session.calibrate(2)
        self.assertIn('4 seconds', session.controller.status)
        for tick in range(20, 60):
            session.step(NEUTRAL, tick / 10)
        self.assertFalse(session.controller.calibrated)
        session.prepare_camera_switch()
        session.step(NEUTRAL, 6.0)
        self.assertTrue(session.controller.calibrated)
        self.assertFalse(session.controller.active)

    def test_connection_and_calibration_do_not_move_robot(self):
        device = Device()
        session = self.prepare(device)
        self.assertTrue(session.controller.calibrated)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands, ['hello', 'off', 'resume', (90,)*4])

    def test_pause_syncs_held_firmware_output_and_preserves_calibration(self):
        device = Device()
        session = self.prepare(device)
        self.assertTrue(session.resume(1.11))
        session.pause()
        self.assertFalse(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertEqual(session.controller.angles, (91,92,93,94))
        self.assertEqual(device.commands[-1], 'hold')
        session.step(Observation(-50,30,20,.2), 1.2)
        self.assertFalse(session.controller.active)
        self.assertEqual(session.controller.angles, (91,92,93,94))

    def test_usb_failure_preserves_active_intent_and_calibration(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        device.fail = True
        session.step(NEUTRAL, 1.2)
        self.assertFalse(session.connected)
        self.assertTrue(session.controller.calibrated)
        self.assertTrue(session.controller.active)
        commands_after_failure = list(device.commands)
        self.assertTrue(session.resume(1.21))
        session.step(Observation(-60,30,20,.2), 1.3)
        self.assertEqual(device.commands, commands_after_failure)
        self.assertTrue(session.controller.active)

    def test_prolonged_tracking_loss_holds_angles_without_pausing_or_sending_hold(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        held = session.controller.angles
        for i in range(7):
            session.step(Observation(None,None,None,None), 1.2+i*.1)
            self.assertTrue(session.controller.active)
            self.assertEqual(session.controller.angles, held)
        self.assertNotIn('hold', device.commands)
        session.step(Observation(-60,30,20,.2), 1.9)
        self.assertTrue(session.controller.active)
        self.assertGreater(session.controller.angles[0], held[0])

    def test_send_rate_is_capped_without_queueing(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        before = len(device.commands)
        for i in range(100):
            session.step(NEUTRAL, 1.12+i*.001)
        sent = [x for x in device.commands[before:] if isinstance(x, tuple)]
        self.assertLessEqual(len(sent), 3)

    def test_dry_run_needs_no_serial_connection(self):
        session = self.prepare()
        self.assertTrue(session.resume(1.11))
        session.step(Observation(-80,10,10,.5),1.2)
        self.assertGreater(session.controller.angles[0],90)
        session.close()
        self.assertFalse(session.controller.active)

    def test_camera_recovery_keeps_tracking_active_and_reuses_reference(self):
        session = self.prepare()
        session.frame(NEUTRAL, captured_at=1.10, now=1.10)
        session.resume(1.11)
        for i in range(12):
            session.camera_missing(1.26+i*.03)
            self.assertTrue(session.controller.active)
            self.assertTrue(session.controller.calibrated)
            self.assertEqual(session.controller.angles, (90,)*4)
        session.frame(Observation(-50,30,20,.2), captured_at=1.63, now=1.63)
        self.assertTrue(session.controller.active)
        self.assertGreater(session.controller.angles[0], 90)

    def test_old_capture_timestamp_does_not_pause_or_discard_observation(self):
        session = self.prepare()
        session.frame(NEUTRAL, captured_at=1.1, now=1.1)
        session.resume(1.11)
        session.frame(Observation(-50,30,20,.2), captured_at=1.12, now=1.64)
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertGreater(session.controller.angles[0],90)

    def test_camera_switch_preserves_reference_and_active_intent_without_hold(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        angles = session.controller.angles
        before = list(device.commands)
        session.prepare_camera_switch()
        self.assertEqual(device.commands, before)
        self.assertEqual(session.controller.angles, angles)
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        session.frame(Observation(-60,30,20,.2), captured_at=1.2, now=1.2)
        self.assertGreater(session.controller.angles[0], angles[0])

    def test_resume_before_connection_or_calibration_starts_capture_and_active_intent(self):
        device = Device()
        session = Session(Config(), device)
        self.assertTrue(session.resume(0))
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrating)
        self.assertFalse(session.connected)
        self.assertEqual(device.commands, [])
        session.step(Observation(None,None,None,None), 0.1)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.angles, (90,)*4)
        session.step(NEUTRAL, 4.1)
        self.assertTrue(session.controller.calibrated)
        self.assertTrue(session.controller.active)
        self.assertEqual(device.commands, [])

    def test_calibration_while_active_releases_outputs_without_changing_active_intent(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.step(Observation(-60,30,20,.2), 1.2)
        angles = session.controller.angles
        session.calibrate(1.3)
        self.assertEqual(device.commands[-1], 'off')
        after_off = list(device.commands)
        self.assertTrue(session.controller.active)
        for tick in range(13, 53):
            session.step(Observation(-45,80,45,.2), tick / 10)
            self.assertTrue(session.controller.active)
            self.assertEqual(session.controller.angles, angles)
            self.assertEqual(device.commands, after_off)
        session.step(Observation(-45,80,45,.2), 5.3)
        self.assertTrue(session.controller.calibrated)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.angles, angles)
        self.assertNotIn('hold', device.commands)
        self.assertEqual(device.commands[-2:], ['resume', angles])

    def test_release_ends_after_four_seconds_even_without_camera_or_hands(self):
        for running in (False, True):
            with self.subTest(running=running):
                device = Device()
                session = self.prepare(device)
                if running:
                    session.resume(2)
                session.calibrate(3)
                before = list(device.commands)
                session.tick(6.999)
                self.assertTrue(session.servos_released)
                self.assertEqual(device.commands, before)
                session.tick(7)
                self.assertFalse(session.servos_released)
                self.assertEqual(session.controller.active, running)
                self.assertEqual(device.commands[-2:], ['resume', (90,)*4])
                session.tick(8)
                self.assertEqual(len(device.commands), len(before)+2)

    def test_space_during_countdown_changes_intent_without_enabling_outputs(self):
        device = Device()
        session = self.prepare(device)
        session.calibrate(2)
        before = list(device.commands)
        session.resume(3)
        session.step(NEUTRAL, 3.1)
        self.assertTrue(session.controller.active)
        self.assertEqual(device.commands, before)
        session.pause()
        self.assertEqual(device.commands[-1], 'hold')
        session.tick(6)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands[-2:], ['resume', (91,92,93,94)])

    def test_repeated_calibration_restarts_release_countdown(self):
        device = Device()
        session = self.prepare(device)
        session.calibrate(2)
        session.calibrate(4)
        before = list(device.commands)
        session.tick(6)
        self.assertTrue(session.servos_released)
        self.assertEqual(device.commands, before)
        session.tick(8)
        self.assertFalse(session.servos_released)

    def test_keyboard_cancels_countdown_and_restores_outputs_before_moving(self):
        for running in (False, True):
            with self.subTest(running=running):
                device = Device()
                session = self.prepare(device)
                if running:
                    session.resume(2)
                session.calibrate(3)
                session.nudge(6, 7, 4)
                self.assertFalse(session.servos_released)
                self.assertFalse(session.controller.calibrating)
                self.assertTrue(session.controller.active)
                self.assertEqual(device.commands[-2:], ['resume', (97,90,90,90)])
                before = list(device.commands)
                session.tick(7)
                self.assertEqual(device.commands, before)

    def test_reconnect_during_countdown_releases_outputs_again(self):
        device = Device()
        session = self.prepare(device)
        session.resume(2)
        session.calibrate(3)
        session.connect()
        self.assertEqual(device.commands[-3:], ['close', 'hello', 'off'])
        self.assertTrue(session.controller.active)
        session.tick(7)
        self.assertEqual(device.commands[-2:], ['resume', (90,)*4])

    def test_release_and_restore_failures_preserve_run_intent(self):
        for fail_stage in ('off', 'restore'):
            with self.subTest(fail_stage=fail_stage):
                device = Device()
                session = self.prepare(device)
                session.resume(2)
                device.fail = fail_stage == 'off'
                session.calibrate(3)
                device.fail = True
                session.tick(7)
                self.assertFalse(session.connected)
                self.assertTrue(session.controller.active)
                self.assertEqual(device.commands[-1], 'close')

    def test_missing_channels_hold_only_their_own_angles(self):
        session = self.prepare()
        session.resume(1.11)
        angles = session.controller.angles
        session.step(Observation(None,30,None,1), 1.2)
        self.assertEqual(session.controller.angles[0], angles[0])
        self.assertGreater(session.controller.angles[1], angles[1])
        self.assertEqual(session.controller.angles[2], angles[2])
        self.assertTrue(session.controller.active)

    def test_large_frame_gap_does_not_pause_or_discard_reference(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.frame(Observation(-60,30,20,.2), captured_at=10, now=10)
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertNotIn('hold', device.commands)

    def test_reconnect_syncs_actual_angles_and_resumes_preserved_active_intent(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        device.fail = True
        session.step(NEUTRAL, 1.2)
        device.fail = False
        device.connect_angles = (70,80,90,100)
        before = len(device.commands)
        session.connect()
        self.assertTrue(session.connected)
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertEqual(session.controller.angles, (70,80,90,100))
        self.assertEqual(device.commands[before:before+2], ['hello', 'resume'])

    def test_reconnect_preserves_manual_pause_without_resuming_device(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.pause()
        device.connect_angles = (70,80,90,100)
        before = len(device.commands)
        session.connect()
        self.assertTrue(session.connected)
        self.assertFalse(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertEqual(session.controller.angles, (70,80,90,100))
        self.assertNotIn('resume', device.commands[before:])

    def test_failed_reconnect_preserves_calibration_and_active_intent(self):
        for fail_stage in ('connect', 'resume'):
            with self.subTest(fail_stage=fail_stage):
                device = Device()
                session = self.prepare(device)
                session.resume(1.11)
                setattr(device, f'{fail_stage}_error', LinkError('port unavailable'))
                session.connect()
                self.assertFalse(session.connected)
                self.assertTrue(session.controller.active)
                self.assertTrue(session.controller.calibrated)

    def test_quit_explicitly_stops_and_closes_connection(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.close()
        self.assertFalse(session.controller.active)
        self.assertFalse(session.connected)
        self.assertEqual(device.commands[-1], 'close')

    def test_keyboard_nudges_each_physical_pin_without_camera_or_calibration(self):
        for pin, want in ((6, (95,90,90,90)), (7, (90,95,90,90)),
                          (8, (90,90,95,90)), (9, (90,90,90,95))):
            with self.subTest(pin=pin):
                session = Session(Config())
                session.nudge(pin, 5, 0)
                self.assertEqual(session.control_mode, 'keyboard')
                self.assertTrue(session.controller.active)
                self.assertFalse(session.controller.calibrated)
                self.assertEqual(session.controller.angles, want)
                session.nudge(pin, -5, .01)
                self.assertEqual(session.controller.angles, (90,)*4)

    def test_keyboard_direct_angles_ignore_tracking_gain_and_direction(self):
        config = Config(joints=(JointConfig(direction=-1, gain=2),
                                JointConfig(), JointConfig(), JointConfig()))
        session = Session(config)
        session.nudge(6, 5, 0)
        self.assertEqual(session.controller.angles, (95,90,90,90))
        session.nudge(6, -5, .01)
        self.assertEqual(session.controller.angles, (90,90,90,90))
        session.nudge(6, -5, .02)
        self.assertEqual(session.controller.angles, (85,90,90,90))

    def test_keyboard_nudges_send_immediately_even_inside_camera_send_interval(self):
        device = Device()
        session = Session(Config(), device)
        session.connect()
        session.nudge(6, 5, 0)
        self.assertEqual(device.commands[-1], (95,90,90,90))
        before = len(device.commands)
        session.nudge(6, 5, .001)
        self.assertIn((100,90,90,90), device.commands[before:])
        self.assertEqual(session.controller.angles, (100,90,90,90))

    def test_keyboard_targets_are_not_overwritten_by_camera_frames_or_camera_loss(self):
        session = self.prepare()
        session.nudge(6, 5, 1.2)
        session.nudge(9, -5, 1.21)
        angles = session.controller.angles
        session.frame(Observation(-30,80,60,.2), captured_at=1.3, now=1.3)
        session.step(Observation(-60,40,30,.3), 1.4)
        session.camera_missing(2)
        session.prepare_camera_switch()
        self.assertEqual(session.controller.angles, angles)
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)

    def test_keyboard_pause_resume_needs_no_calibration_and_uses_actual_held_angles(self):
        device = Device()
        session = Session(Config(), device)
        session.connect()
        session.nudge(6, 5, 0)
        session.pause()
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertFalse(session.controller.active)
        self.assertEqual(session.controller.angles, (91,92,93,94))
        self.assertTrue(session.resume(.1))
        self.assertTrue(session.controller.active)
        self.assertFalse(session.controller.calibrated)
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertEqual(device.commands[-1], (91,92,93,94))
        session.camera_missing(.2)
        self.assertEqual(session.controller.angles, (91,92,93,94))

    def test_keyboard_key_after_pause_starts_and_nudges_actual_held_position(self):
        device = Device()
        session = Session(Config(), device)
        session.connect()
        session.nudge(6, 5, 0)
        session.pause()
        session.nudge(7, 5, .1)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.angles, (91,97,93,94))
        self.assertEqual(device.commands[-1], (91,97,93,94))

    def test_keyboard_offline_changes_do_not_require_or_open_serial(self):
        device = Device()
        session = Session(Config(), device)
        session.nudge(8, -5, 0)
        session.camera_missing(10)
        self.assertEqual(session.controller.angles, (90,90,85,90))
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertTrue(session.controller.active)
        self.assertFalse(session.connected)
        self.assertFalse(session.controller.calibrated)
        self.assertEqual(device.commands, [])

    def test_keyboard_send_failure_and_reconnect_preserve_mode_and_run_intent(self):
        device = Device()
        session = Session(Config(), device)
        session.connect()
        device.fail = True
        session.nudge(6, 5, 0)
        self.assertFalse(session.connected)
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertTrue(session.controller.active)
        device.fail = False
        device.connect_angles = (70,80,90,100)
        before = len(device.commands)
        session.connect()
        self.assertTrue(session.connected)
        self.assertEqual(session.control_mode, 'keyboard')
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.angles, (70,80,90,100))
        self.assertIn('resume', device.commands[before:])
        session.nudge(6, 5, .1)
        self.assertEqual(device.commands[-1], (75,80,90,100))

    def test_use_tracking_preserves_existing_reference_and_active_or_paused_state(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                session = self.prepare()
                session.nudge(6, 5, 1.2)
                if paused:
                    session.pause()
                before = session.controller.angles
                session.use_tracking(1.3)
                self.assertEqual(session.control_mode, 'tracking')
                self.assertEqual(session.controller.active, not paused)
                self.assertTrue(session.controller.calibrated)
                self.assertEqual(session.controller.angles, before)
                session.frame(Observation(-40,60,50,.2), captured_at=1.4, now=1.4)
                if paused:
                    self.assertEqual(session.controller.angles, before)
                else:
                    self.assertGreater(session.controller.angles[0], before[0])

    def test_tracking_after_uncalibrated_keyboard_captures_reference_without_manual_calibration(self):
        session = Session(Config())
        session.nudge(6, 5, 0)
        session.use_tracking(.1)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.control_mode, 'tracking')
        session.frame(NEUTRAL, captured_at=.2, now=.2)
        self.assertTrue(session.controller.calibrated)
        session.frame(Observation(-40,60,50,.2), captured_at=.3, now=.3)
        self.assertGreater(session.controller.angles[0], 95)

    def test_calibrate_from_keyboard_selects_tracking_and_preserves_run_state(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                session = Session(Config())
                session.nudge(6, 5, 0)
                if paused:
                    session.pause()
                angles = session.controller.angles
                session.calibrate(.1)
                self.assertEqual(session.control_mode, 'tracking')
                self.assertEqual(session.controller.active, not paused)
                self.assertTrue(session.controller.calibrating)
                session.step(NEUTRAL, 4.0)
                self.assertEqual(session.controller.angles, angles)
                self.assertFalse(session.controller.calibrated)
                session.step(NEUTRAL, 4.1)
                self.assertTrue(session.controller.calibrated)
                self.assertEqual(session.controller.active, not paused)

    def test_signed_positions_map_to_extended_wire_angles_on_every_servo(self):
        for pin in (6,7,8,9):
            for position, wire_angle in ((-360,-270), (-180,-90), (-90,0), (-45,45), (0,90), (90,180), (180,270), (360,450)):
                with self.subTest(pin=pin, position=position):
                    device = Device()
                    session = Session(Config(), device)
                    session.connect()
                    session.set_position(pin, position, 0)
                    expected = [90,90,90,90]
                    expected[pin-6] = wire_angle
                    self.assertEqual(session.controller.angles, tuple(expected))
                    self.assertEqual(device.commands[-1], tuple(expected))
                    self.assertEqual(session.controller.positions[pin-6], position)
                    self.assertEqual(session.control_mode, 'keyboard')
                    self.assertTrue(session.controller.active)
                    self.assertFalse(session.controller.calibrated)

    def test_set_position_is_absolute_after_prior_keyboard_movement(self):
        session = Session(Config())
        session.nudge(7, 20, 0)
        session.set_position(7, -45, .1)
        self.assertEqual(session.controller.angles, (90,45,90,90))
        session.set_position(7, 0, .2)
        self.assertEqual(session.controller.angles, (90,90,90,90))

    def test_keyboard_negative_steps_report_signed_position_below_center(self):
        for pin in (6,7,8,9):
            with self.subTest(pin=pin):
                session = Session(Config())
                session.nudge(pin, -5, 0)
                self.assertEqual(session.controller.angles[pin-6], 85)
                self.assertEqual(session.controller.positions[pin-6], -5)
                self.assertIn(f'IO{pin} -5 degrees', session.controller.status)

    def test_invalid_signed_position_does_not_change_run_mode_or_send_commands(self):
        for position in (-2**31-91, 2**31-90, float('nan'), float('inf'), -float('inf'),
                         True, '-45', None, 10**1000):
            with self.subTest(position=position):
                device = Device()
                session = Session(Config(), device)
                session.connect()
                with self.assertRaises(ValueError):
                    session.set_position(6, position, 0)
                self.assertEqual(session.controller.angles, (90,)*4)
                self.assertFalse(session.controller.active)
                self.assertEqual(session.control_mode, 'tracking')
                self.assertEqual(device.commands, ['hello'])

    def test_signed_positions_reject_non_servo_pins_before_mutation(self):
        for pin in (5,10,True,6.0,'6'):
            with self.subTest(pin=pin):
                session = Session(Config())
                with self.assertRaises(ValueError):
                    session.set_position(pin, -45, 0)
                self.assertEqual(session.controller.angles, (90,)*4)
                self.assertFalse(session.controller.active)

    def prepare_manual_zero(self, device=None):
        session = Session(Config(), device)
        if device:
            session.connect()
        for pin, position in ((6,-30), (7,45), (8,120), (9,-15)):
            session.set_position(pin, position, 0)
        session.calibrate(1)
        reference = Observation(-45,40,20,.6)
        session.step(reference, 5)
        return session, reference

    def test_calibration_sets_all_current_manual_servo_angles_as_displayed_zero(self):
        session, reference = self.prepare_manual_zero()
        self.assertEqual(session.controller.angles, (60,135,210,75))
        self.assertEqual(session.controller.zero_angles, (60,135,210,75))
        self.assertEqual(session.controller.positions, (0,0,0,0))
        self.assertTrue(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        session.step(reference, 5.1)
        self.assertEqual(session.controller.angles, (60,135,210,75))
        self.assertEqual(session.controller.positions, (0,0,0,0))

    def test_zero_and_signed_targets_use_each_calibrated_servo_origin(self):
        device = Device()
        session, _ = self.prepare_manual_zero(device)
        for pin, zero in ((6,60), (7,135), (8,210), (9,75)):
            for position in (-45,30,0):
                with self.subTest(pin=pin, position=position):
                    session.set_position(pin, position, 5.1)
                    expected = [60,135,210,75]
                    expected[pin-6] = zero + position
                    self.assertEqual(session.controller.angles, tuple(expected))
                    self.assertEqual(device.commands[-1], tuple(expected))
                    self.assertEqual(session.controller.positions[pin-6], position)
                    self.assertEqual(session.controller.zero_angles, (60,135,210,75))

    def test_keyboard_steps_after_calibration_are_relative_to_saved_zero(self):
        session, _ = self.prepare_manual_zero()
        session.nudge(7, 5, 5.1)
        session.nudge(8, -5, 5.2)
        self.assertEqual(session.controller.angles, (60,140,205,75))
        self.assertEqual(session.controller.positions, (0,5,-5,0))
        self.assertEqual(session.controller.zero_angles, (60,135,210,75))
        self.assertIn('IO8 -5 degrees', session.controller.status)

    def test_reconnect_syncs_raw_angles_without_replacing_calibrated_zero(self):
        device = Device()
        session, _ = self.prepare_manual_zero(device)
        device.connect_angles = (63,132,217,70)
        session.connect()
        self.assertEqual(session.controller.angles, (63,132,217,70))
        self.assertEqual(session.controller.zero_angles, (60,135,210,75))
        self.assertEqual(session.controller.positions, (3,-3,7,-5))
        self.assertTrue(session.controller.calibrated)
        self.assertTrue(session.controller.active)
        session.set_position(7, 0, 5.1)
        self.assertEqual(device.commands[-1], (63,135,217,70))

    def test_protocol_limits_are_relative_to_calibrated_zero_and_invalid_target_is_atomic(self):
        for zero, boundary, valid_position, invalid_position in (
            (-100, 2147483647, 2147483747, 2147483748),
            (200, -2147483648, -2147483848, -2147483849),
        ):
            with self.subTest(zero=zero):
                device = Device()
                session = Session(Config(), device)
                session.connect()
                session.set_position(6, zero-90, 0)
                session.calibrate(1)
                session.step(NEUTRAL, 5)
                session.set_position(6, valid_position, 5.1)
                self.assertEqual(session.controller.angles[0], boundary)
                self.assertEqual(session.controller.positions[0], valid_position)
                before = (session.controller.angles, session.control_mode,
                          session.controller.active, list(device.commands))
                with self.assertRaises(ValueError):
                    session.set_position(6, invalid_position, 5.2)
                self.assertEqual((session.controller.angles, session.control_mode,
                                  session.controller.active, device.commands), before)


if __name__ == '__main__':
    unittest.main()
