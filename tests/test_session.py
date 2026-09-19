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

    def connect(self):
        self.commands.append('hello')
        return (90,)*4

    def resume(self):
        self.commands.append('resume')

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
        self.assertFalse(session.resume(3.9))
        session.step(Observation(-45,90,60,.2), 4.0)
        self.assertTrue(session.controller.calibrated)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands, ['hello', 'hold'])

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
        for tick in range(60, 80):
            session.step(NEUTRAL, tick / 10)
        self.assertFalse(session.controller.calibrated)

    def test_connection_and_calibration_do_not_move_robot(self):
        device = Device()
        session = self.prepare(device)
        self.assertTrue(session.controller.calibrated)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands, ['hello', 'hold'])

    def test_pause_syncs_held_firmware_output_and_preserves_calibration(self):
        device = Device()
        session = self.prepare(device)
        self.assertTrue(session.resume(1.11))
        session.pause()
        self.assertFalse(session.controller.active)
        self.assertTrue(session.controller.calibrated)
        self.assertEqual(session.controller.angles, (91,92,93,94))

    def test_usb_failure_clears_calibration_and_prevents_resume(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        device.fail = True
        session.step(NEUTRAL, 1.2)
        self.assertFalse(session.connected)
        self.assertFalse(session.controller.calibrated)
        self.assertFalse(session.resume(1.21))

    def test_prolonged_tracking_loss_sends_hold_and_never_auto_resumes(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        for i in range(7):
            session.step(Observation(None,None,None,None), 1.2+i*.1)
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands[-1], 'hold')
        session.step(NEUTRAL, 1.9)
        self.assertFalse(session.controller.active)

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

    def test_camera_recovery_after_half_second_requires_explicit_resume(self):
        session = self.prepare()
        session.frame(NEUTRAL, captured_at=1.10, now=1.10)
        session.resume(1.11)
        for i in range(12):
            session.camera_missing(1.26+i*.03)
        session.frame(Observation(-50,30,20,.2), captured_at=1.63, now=1.63)
        self.assertFalse(session.controller.active)
        self.assertEqual(session.controller.angles, (90,)*4)

    def test_old_captured_frame_cannot_move_even_if_inference_is_fresh(self):
        session = self.prepare()
        session.frame(NEUTRAL, captured_at=1.1, now=1.1)
        session.resume(1.11)
        session.frame(Observation(-50,30,20,.2), captured_at=1.12, now=1.64)
        self.assertFalse(session.controller.active)
        self.assertEqual(session.controller.angles,(90,)*4)

    def test_camera_switch_holds_actual_angles_and_requires_new_calibration(self):
        device = Device()
        session = self.prepare(device)
        session.resume(1.11)
        session.prepare_camera_switch()
        self.assertEqual(device.commands[-1], 'hold')
        self.assertEqual(session.controller.angles, (91,92,93,94))
        self.assertFalse(session.controller.active)
        self.assertFalse(session.controller.calibrated)
        session.frame(NEUTRAL, captured_at=1.2, now=1.2)
        self.assertFalse(session.resume(1.21))


if __name__ == '__main__':
    unittest.main()
