import contextlib
import io
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import numpy as np

from arm_control.app import _display, run
from arm_control.camera import CapturedFrame
from arm_control.config import Config
from arm_control.control import Observation
from arm_control.session import Session
from arm_control.keyboard import KeyRepeater


class AppCameraTests(unittest.TestCase):
    def exercise(self, keys, failed_first=False, pending_probes=False, frame_plan=None,
                 camera_failures=(), tracker_failures=(), tracker_close_failures=(), servo_keys=None):
        cameras, trackers, panels, sessions, states, processed = [], [], [], [], [], []
        tracker_attempts, displays = [], []
        errors = io.StringIO()
        keys = iter(keys)
        planned_frames = iter(frame_plan) if frame_plan is not None else None
        clock = [0.0]

        class FakeCamera:
            def __init__(self, index, width, height):
                self.index, self.sequence, self.closed = index, 0, False
                self.error = 'camera unavailable' if failed_first and index == 0 else None
                cameras.append(self)
                if len(cameras) in camera_failures:
                    self.error = 'camera unavailable'

            def start(self):
                return self

            def latest(self, after=-1, timeout=0):
                if self.error:
                    return None
                if pending_probes and self.index != 0:
                    return None
                if planned_frames is not None:
                    clock[0], available = next(planned_frames)
                    if not available:
                        return None
                self.sequence += 1
                return CapturedFrame(self.sequence,time.monotonic(),np.full((240,320,3),self.index+1,dtype=np.uint8))

            def close(self):
                self.closed = True

        class FakeTracker:
            def __init__(self, config, models):
                tracker_attempts.append(True)
                if len(tracker_attempts) in tracker_failures:
                    raise RuntimeError('model creation failed')
                self.closed = False
                self.close_count = 0
                self.attempt = len(tracker_attempts)
                trackers.append(self)

            def process(self, image, captured_at):
                processed.append(captured_at)
                return Observation(-90,0,0,1), {}, NS(pose_landmarks=[]), NS(hand_landmarks=[])

            def close(self):
                self.close_count += 1
                self.closed = True
                if self.attempt in tracker_close_failures:
                    raise RuntimeError('model cleanup failed')

        def display(*args):
            displays.append(NS(value=float(args[0].mean()), pose=args[1], hands=args[2],
                               observation=args[4], status=args[-1]))
            return _display(*args)

        def show(name, panel):
            panels.append(panel.shape)

        def make_session(*args):
            session = Session(*args)
            sessions.append(session)
            return session

        def next_key(delay):
            controller = sessions[0].controller
            states.append((controller.active, controller.calibrating))
            return next(keys)

        args = NS(dry_run=True,port=None,models=None,headless=False,frames=0)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch('arm_control.app.create_servo_keys', return_value=servo_keys))
            if planned_frames is not None:
                stack.enter_context(patch('arm_control.app.time.monotonic', side_effect=lambda: clock[0]))
            with patch('arm_control.camera.Camera',FakeCamera), patch('arm_control.vision.Tracker',FakeTracker), \
             patch('arm_control.app.Session',side_effect=make_session), \
             patch('arm_control.app._display',side_effect=display), \
             patch('cv2.namedWindow'), patch('cv2.resizeWindow'), patch('cv2.destroyAllWindows'), \
             patch('cv2.getWindowProperty',return_value=1), patch('cv2.imshow',side_effect=show), \
             patch('cv2.waitKey',side_effect=next_key), contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(errors):
                self.assertEqual(run(Config(width=320,height=240),args),0)
        return NS(cameras=cameras, trackers=trackers, panels=panels,
                  states=states, processed=processed, session=sessions[0],
                  tracker_attempts=tracker_attempts, displays=displays, errors=errors.getvalue())

    def test_failed_scan_keeps_existing_tracker(self):
        result = self.exercise([ord('v'),-1,-1,-1,ord('q')],camera_failures=(2,3,4))
        self.assertEqual(len(result.trackers),1)
        self.assertEqual(result.trackers[0].close_count,1)
        self.assertGreater(len(result.processed),1)

    def test_probing_keeps_preview_without_stale_landmarks(self):
        result = self.exercise([ord('v'),-1,ord('q')],pending_probes=True)
        self.assertEqual([display.value for display in result.displays],[1,1,1])
        for display in result.displays[1:]:
            self.assertIsNone(display.pose)
            self.assertIsNone(display.hands)
            self.assertEqual(display.observation,Observation(None,None,None,None))

    def test_replacement_failure_keeps_ui_and_run_state_then_v_recovers(self):
        result = self.exercise([32,ord('v'),-1,ord('v'),-1,ord('q')],tracker_failures=(2,))
        self.assertEqual(len(result.tracker_attempts),3)
        self.assertTrue(all(t.close_count == 1 for t in result.trackers))
        self.assertEqual([active for active,_ in result.states],[False,True,True,True,True,True])
        failed = result.displays[2]
        self.assertEqual(failed.value,2)
        self.assertIsNone(failed.pose)
        self.assertIn('model creation failed',failed.status)
        self.assertIn('V',failed.status)
        self.assertIn('Traceback (most recent call last)',result.errors)
        self.assertIn('model creation failed',result.errors)
        self.assertIsNotNone(result.displays[-1].pose)

    def test_replacement_cleanup_failure_does_not_reclose_old_tracker(self):
        result = self.exercise([ord('v'),-1,ord('v'),-1,ord('q')],tracker_close_failures=(1,))
        self.assertTrue(all(t.close_count == 1 for t in result.trackers))
        self.assertIn('model cleanup failed',result.displays[1].status)
        self.assertIsNotNone(result.displays[-1].pose)

    def test_v_retries_failed_tracker_even_when_no_camera_changes(self):
        result = self.exercise([ord('v'),-1,ord('v'),-1,-1,-1,ord('q')],
                               camera_failures=(3,4,5),tracker_failures=(2,))
        self.assertEqual(len(result.tracker_attempts),3)
        self.assertIsNotNone(result.displays[-1].pose)
        self.assertEqual(result.displays[-1].value,2)
        self.assertTrue(all(t.close_count == 1 for t in result.trackers))

    def test_v_switches_camera_and_restarts_landmark_tracking(self):
        result = self.exercise([ord('v'),-1,ord('q')])
        self.assertEqual([c.index for c in result.cameras],[0,1])
        self.assertEqual(len(result.trackers),2)
        self.assertTrue(all(c.closed for c in result.cameras))
        self.assertTrue(all(t.closed for t in result.trackers))
        self.assertTrue(result.panels)

    def test_keyboard_switch_recovers_from_no_startup_camera(self):
        result = self.exercise([ord('v'),-1,ord('q')],failed_first=True)
        self.assertEqual([c.index for c in result.cameras],[0,1])
        self.assertGreaterEqual(len(result.panels),2)
        self.assertTrue(all(c.closed for c in result.cameras))

    def test_fresh_frames_recover_after_stall_longer_than_ten_seconds(self):
        result = self.exercise(
            [32,-1,-1,ord('q')],
            frame_plan=[(1.0,True),(12.0,False),(12.1,True),(12.2,True)],
        )
        self.assertEqual(result.processed, [1.0,12.1,12.2])
        self.assertEqual([active for active, _ in result.states], [False,True,True,True])
        self.assertTrue(result.session.controller.calibrated)

    def test_space_toggles_and_c_preserves_run_state_with_failed_camera(self):
        result = self.exercise([32,ord('c'),32,ord('c'),ord('q')],failed_first=True)
        self.assertEqual([active for active, _ in result.states], [False,True,True,False,False])
        self.assertTrue(result.states[-1][1])
        self.assertEqual(result.processed, [])

    def test_space_toggles_and_c_preserves_run_state_while_probing(self):
        result = self.exercise(
            [32,ord('v'),32,ord('c'),32,ord('c'),ord('q')],pending_probes=True,
        )
        self.assertEqual([active for active, _ in result.states],
                         [False,True,True,False,False,True,True])
        self.assertFalse(result.states[3][1])
        self.assertTrue(result.states[4][1])
        self.assertEqual([c.index for c in result.cameras], [0,1])
        self.assertEqual(len(result.trackers), 1)
        self.assertTrue(all(c.closed for c in result.cameras))

    def test_c_preserves_running_and_paused_states_with_working_camera(self):
        result = self.exercise([32,-1,ord('c'),-1,32,ord('c'),ord('q')])
        self.assertEqual([active for active, _ in result.states],
                         [False,True,True,True,True,False,False])
        self.assertTrue(result.states[3][1])
        self.assertTrue(result.states[-1][1])

    def test_servo_keys_address_all_four_pins_without_a_camera(self):
        result = self.exercise([ord(k) for k in '1473q'],failed_first=True)
        self.assertEqual(result.session.controller.angles,(83,83,83,83))
        self.assertEqual(result.session.control_mode,'keyboard')
        self.assertEqual([active for active,_ in result.states],[False,True,True,True,True])

    def test_numpad_decrease_and_increase_pairs_restore_all_four_angles(self):
        result = self.exercise([ord(k) for k in '14732586q'])
        self.assertEqual(result.session.controller.angles,(90,)*4)
        self.assertEqual(result.session.control_mode,'keyboard')

    def test_tracking_does_not_overwrite_keyboard_and_m_restores_tracking(self):
        result = self.exercise([ord('2'),-1,-1,ord('q')])
        self.assertEqual(result.session.controller.angles,(97,90,90,90))
        result = self.exercise([ord('2'),ord('m'),-1,ord('q')])
        self.assertEqual(result.session.control_mode,'tracking')
        self.assertTrue(result.session.controller.calibrated)

    def test_held_key_cannot_undo_pause_or_tracking_selection(self):
        class HeldKey:
            def __init__(self):
                self.repeater = KeyRepeater(45)
                self.repeater.event(0x62, 1, 0)
                self.closed = False

            def poll(self, now):
                return self.repeater.poll(now, {0x62})

            def cancel(self):
                self.repeater.cancel()

            def close(self):
                self.closed = True

        for command in (32, ord('m'), ord('c')):
            with self.subTest(command=command):
                held = HeldKey()
                result = self.exercise([-1, command, -1, ord('q')], servo_keys=held,
                                       frame_plan=[(0, True), (.6, True), (.7, True), (.8, True)])
                self.assertTrue(held.closed)
                if command == 32:
                    self.assertFalse(result.session.controller.active)
                    self.assertEqual(result.session.controller.angles, (97,90,90,90))
                else:
                    self.assertEqual(result.session.control_mode, 'tracking')
                    self.assertTrue(result.states[-1][0])

    def test_repeat_counts_combine_by_servo_with_seven_degree_steps(self):
        keys = Mock()
        keys.poll.side_effect = [{ord('1'): 2, ord('2'): 1, ord('5'): 3}]
        result = self.exercise([-1, ord('q')], servo_keys=keys)
        self.assertEqual(result.session.controller.angles, (83,111,90,90))
        self.assertEqual(result.session.control_mode, 'keyboard')
        keys.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
