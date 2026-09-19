import unittest

from arm_control.config import Config
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
        self.assertEqual(device.commands, ['hello'])

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
        self.assertEqual(device.commands, ['hello'])

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

    def test_calibration_while_active_holds_angles_without_changing_active_intent(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.step(Observation(-60,30,20,.2), 1.2)
        angles = session.controller.angles
        session.calibrate(1.3)
        self.assertTrue(session.controller.active)
        for tick in range(13, 53):
            session.step(Observation(-45,80,45,.2), tick / 10)
            self.assertTrue(session.controller.active)
            self.assertEqual(session.controller.angles, angles)
        session.step(Observation(-45,80,45,.2), 5.3)
        self.assertTrue(session.controller.calibrated)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.angles, angles)
        self.assertNotIn('hold', device.commands)

    def test_missing_channels_hold_only_their_own_angles(self):
        session = self.prepare()
        session.resume(1.11)
        angles = session.controller.angles
        session.step(Observation(None,30,None,1), 1.2)
        self.assertEqual(session.controller.angles[0], angles[0])
        self.assertEqual(session.controller.angles[2], angles[2])
        self.assertGreater(session.controller.angles[1], angles[1])
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


if __name__ == '__main__':
    unittest.main()
