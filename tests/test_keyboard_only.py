import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from arm_control.keyboard import SERVO_KEYS
from arm_control.keyboard_only import KeyboardSession, KeyboardWindow, build_parser
from arm_control.transport import LinkError


class Device:
    def __init__(self):
        self.angles = (90,) * 4
        self.commands = []
        self.fail = False

    def connect(self):
        self.commands.append('hello')
        return self.angles

    def resume(self):
        self.commands.append('resume')

    def send_pose(self, angles):
        if self.fail:
            raise LinkError('USB disconnected')
        self.angles = tuple(angles)
        self.commands.append(self.angles)

    def hold(self):
        self.commands.append('hold')
        return self.angles

    def close(self):
        self.commands.append('close')


class KeyboardOnlyTests(unittest.TestCase):
    def test_controls_guide_preserves_running_state_and_servo_commands(self):
        window = KeyboardWindow.__new__(KeyboardWindow)
        window.keys = Mock()
        window.view = Mock()
        window.render = Mock()
        window.session = Mock()
        window.command('f1')
        window.view.toggle_controls.assert_called_once()
        self.assertEqual(window.session.mock_calls, [])

    def test_holding_f1_toggles_guide_only_once_until_released(self):
        window = KeyboardWindow.__new__(KeyboardWindow)
        window.keys = Mock()
        window.pressed_commands = set()
        window.command = Mock()
        for _ in range(5):
            window.key_down(Mock(keysym='F1'))
        window.command.assert_called_once_with('f1')
        window.key_up(Mock(keysym='F1'))
        window.key_down(Mock(keysym='F1'))
        self.assertEqual(window.command.call_count, 2)

    def test_fullscreen_refreshes_native_key_ownership(self):
        window = KeyboardWindow.__new__(KeyboardWindow)
        window.root = Mock()
        window.root.attributes.return_value = False
        window.root.title.return_value = 'Robot arm - Keyboard'
        window.keys = old_keys = Mock()
        window.view = Mock()
        window.render = Mock()
        replacement = Mock()
        with patch('arm_control.keyboard_only.create_servo_keys', return_value=replacement) as create:
            window.command('f11')
        old_keys.cancel.assert_called_once()
        old_keys.close.assert_called_once()
        window.root.attributes.assert_any_call('-fullscreen', True)
        window.root.update_idletasks.assert_called_once()
        create.assert_called_once_with('Robot arm - Keyboard')
        self.assertIs(window.keys, replacement)

    def test_enter_activates_focused_button_once_until_released(self):
        window = KeyboardWindow.__new__(KeyboardWindow)
        window.pressed_commands = set()
        button = Mock()
        for _ in range(10):
            self.assertEqual(window.activate_button(button), 'break')
        button.invoke.assert_called_once()
        window.key_up(Mock(keysym='Return'))
        window.activate_button(button)
        self.assertEqual(button.invoke.call_count, 2)

    def test_tk_callback_failure_closes_resources_and_propagates_from_run(self):
        window = KeyboardWindow.__new__(KeyboardWindow)
        window.root = Mock()
        window.session = Mock(connection_status='Preview only')
        window.keys = Mock()
        window.closed = False
        window.after_id = 'timer'
        window.callback_error = None
        window.tick = Mock()
        error = RuntimeError('callback failed')
        window.root.mainloop.side_effect = lambda: window.callback_failed(RuntimeError, error, None)
        with self.assertRaisesRegex(RuntimeError, 'callback failed'):
            window.run()
        window.session.close.assert_called_once()
        window.keys.close.assert_called_once()
        window.root.destroy.assert_called_once()

    def test_no_tracking_update_or_reference_required(self):
        session = KeyboardSession()
        with patch.object(session.controller, 'update', side_effect=AssertionError('tracking ran')):
            session.resume(0)
            session.tick(10)
            self.assertTrue(session.controller.active)
            self.assertFalse(session.controller.calibrating)
            self.assertIsNone(session.controller._reference)
            self.assertNotIn('tracking', session.controller.status.lower())

    def test_every_key_pair_moves_immediately_and_resumes(self):
        for digit, (pin, delta) in SERVO_KEYS.items():
            with self.subTest(digit=chr(digit)):
                device = Device()
                session = KeyboardSession(device)
                session.connect()
                self.assertFalse(session.controller.active)
                session.nudge(pin, delta, 0)
                self.assertTrue(session.controller.active)
                expected = [90] * 4
                expected[pin - 6] += delta
                self.assertEqual(device.angles, tuple(expected))
                self.assertIn('resume', device.commands)

    def test_zeroing_waits_four_seconds_without_moving_or_changing_run_state(self):
        for active in (True, False):
            device = Device()
            session = KeyboardSession(device)
            session.connect()
            for pin, delta in ((6, 28), (7, -140), (8, 210), (9, -35)):
                session.nudge(pin, delta, 0)
            if not active:
                session.pause()
            angles = device.angles
            positions = session.controller.positions
            device.commands.clear()
            session.calibrate(1)
            session.tick(4.999)
            self.assertEqual(session.controller.positions, positions)
            session.tick(5)
            self.assertEqual(session.controller.positions, (0,) * 4)
            self.assertEqual(session.controller.angles, angles)
            self.assertEqual(session.controller.active, active)
            self.assertTrue(all(command == angles for command in device.commands))
            session.nudge(8, 7, 5.1)
            self.assertEqual(session.controller.positions, (0, 0, 7, 0))

    def test_new_zero_request_restarts_countdown_and_nudge_cancels_it(self):
        session = KeyboardSession()
        session.nudge(6, 14, 0)
        session.calibrate(1)
        session.calibrate(3)
        session.tick(5)
        self.assertEqual(session.zero_at, 7)
        session.nudge(6, 7, 5.1)
        session.tick(10)
        self.assertIsNone(session.zero_at)
        self.assertEqual(session.controller.positions, (21, 0, 0, 0))

    def test_usb_fault_keeps_run_latch_and_reconnect_preserves_zero(self):
        device = Device()
        session = KeyboardSession(device)
        session.connect()
        session.nudge(6, 7, 0)
        session.calibrate(0)
        session.tick(4)
        zeros = session.controller.zero_angles
        device.fail = True
        session.tick(5)
        self.assertFalse(session.connected)
        self.assertTrue(session.controller.active)
        device.fail = False
        session.connect()
        self.assertTrue(session.connected)
        self.assertTrue(session.controller.active)
        self.assertEqual(session.controller.zero_angles, zeros)

    def test_pause_holds_and_close_releases_connection(self):
        device = Device()
        session = KeyboardSession(device)
        session.connect()
        session.resume(0)
        session.pause()
        self.assertFalse(session.controller.active)
        self.assertEqual(device.commands[-1], 'hold')
        session.close()
        self.assertEqual(device.commands[-1], 'close')

    def test_cli_has_no_camera_or_tracking_options_and_defaults_to_preview(self):
        parser = build_parser()
        self.assertIsNone(parser.parse_args([]).port)
        self.assertEqual(parser.parse_args(['--port', 'COM70']).port, 'COM70')
        for option in ('--camera', '--models', '--download-models', '--list-cameras'):
            self.assertNotIn(option, parser.format_help())

    def test_starts_without_importing_camera_or_model_dependencies(self):
        script = '''
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('cv2', 'numpy', 'mediapipe') or fullname in (
                'arm_control.camera', 'arm_control.vision', 'arm_control.app'):
            raise AssertionError('Camera dependency imported: ' + fullname)
sys.meta_path.insert(0, Block())
from arm_control.keyboard_only import KeyboardSession, build_parser
session = KeyboardSession()
session.nudge(6, 7, 0)
session.calibrate(0)
session.tick(4)
assert session.controller.positions == (0, 0, 0, 0)
assert session.controller.active
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
