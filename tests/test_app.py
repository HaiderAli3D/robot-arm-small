import contextlib
import io
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

from arm_control.app import run
from arm_control.camera import CapturedFrame
from arm_control.config import Config
from arm_control.control import Observation
from arm_control.session import Session


class AppCameraTests(unittest.TestCase):
    def exercise(self, keys, failed_first=False, pending_probes=False, frame_plan=None):
        cameras, trackers, panels, sessions, states, processed = [], [], [], [], [], []
        keys = iter(keys)
        planned_frames = iter(frame_plan) if frame_plan is not None else None
        clock = [0.0]

        class FakeCamera:
            def __init__(self, index, width, height):
                self.index, self.sequence, self.closed = index, 0, False
                self.error = 'camera unavailable' if failed_first and index == 0 else None
                cameras.append(self)

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
                return CapturedFrame(self.sequence,time.monotonic(),np.zeros((240,320,3),dtype=np.uint8))

            def close(self):
                self.closed = True

        class FakeTracker:
            def __init__(self, config, models):
                self.closed = False
                trackers.append(self)

            def process(self, image, captured_at):
                processed.append(captured_at)
                return Observation(-90,0,0,1), {}, NS(pose_landmarks=[]), NS(hand_landmarks=[])

            def close(self):
                self.closed = True

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
            if planned_frames is not None:
                stack.enter_context(patch('arm_control.app.time.monotonic', side_effect=lambda: clock[0]))
            with patch('arm_control.camera.Camera',FakeCamera), patch('arm_control.vision.Tracker',FakeTracker), \
             patch('arm_control.app.Session',side_effect=make_session), \
             patch('cv2.namedWindow'), patch('cv2.resizeWindow'), patch('cv2.destroyAllWindows'), \
             patch('cv2.getWindowProperty',return_value=1), patch('cv2.imshow',side_effect=show), \
             patch('cv2.waitKey',side_effect=next_key), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run(Config(width=320,height=240),args),0)
        return NS(cameras=cameras, trackers=trackers, panels=panels,
                  states=states, processed=processed, session=sessions[0])

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
        result = self.exercise([ord(k) for k in 'wtupq'],failed_first=True)
        self.assertEqual(result.session.controller.angles,(85,85,85,85))
        self.assertEqual(result.session.control_mode,'keyboard')
        self.assertEqual([active for active,_ in result.states],[False,True,True,True,True])

    def test_uppercase_and_increment_keys_restore_all_four_angles(self):
        result = self.exercise([ord(k) for k in 'WTUPEYI[q'])
        self.assertEqual(result.session.controller.angles,(90,)*4)
        self.assertEqual(result.session.control_mode,'keyboard')

    def test_tracking_does_not_overwrite_keyboard_and_m_restores_tracking(self):
        result = self.exercise([ord('e'),-1,-1,ord('q')])
        self.assertEqual(result.session.controller.angles,(95,90,90,90))
        result = self.exercise([ord('e'),ord('m'),-1,ord('q')])
        self.assertEqual(result.session.control_mode,'tracking')
        self.assertTrue(result.session.controller.calibrated)


if __name__ == '__main__':
    unittest.main()
