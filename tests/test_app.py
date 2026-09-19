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


class AppCameraTests(unittest.TestCase):
    def exercise(self, keys, failed_first=False):
        cameras, trackers, panels = [], [], []

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
                self.sequence += 1
                return CapturedFrame(self.sequence,time.monotonic(),np.zeros((240,320,3),dtype=np.uint8))

            def close(self):
                self.closed = True

        class FakeTracker:
            def __init__(self, config, models):
                self.closed = False
                trackers.append(self)

            def process(self, image, captured_at):
                return Observation(-90,0,0,1), {}, NS(pose_landmarks=[]), NS(hand_landmarks=[])

            def close(self):
                self.closed = True

        def show(name, panel):
            panels.append(panel.shape)

        args = NS(dry_run=True,port=None,models=None,headless=False,frames=0)
        with patch('arm_control.camera.Camera',FakeCamera), patch('arm_control.vision.Tracker',FakeTracker), \
             patch('cv2.namedWindow'), patch('cv2.resizeWindow'), patch('cv2.destroyAllWindows'), \
             patch('cv2.getWindowProperty',return_value=1), patch('cv2.imshow',side_effect=show), \
             patch('cv2.waitKey',side_effect=keys), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run(Config(width=320,height=240),args),0)
        return cameras, trackers, panels

    def test_v_switches_camera_and_restarts_landmark_tracking(self):
        cameras, trackers, panels = self.exercise([ord('v'),-1,ord('q')])
        self.assertEqual([c.index for c in cameras],[0,1])
        self.assertEqual(len(trackers),2)
        self.assertTrue(all(c.closed for c in cameras))
        self.assertTrue(all(t.closed for t in trackers))
        self.assertTrue(panels)

    def test_keyboard_switch_recovers_from_no_startup_camera(self):
        cameras, trackers, panels = self.exercise([ord('v'),-1,ord('q')],failed_first=True)
        self.assertEqual([c.index for c in cameras],[0,1])
        self.assertGreaterEqual(len(panels),2)
        self.assertTrue(all(c.closed for c in cameras))


if __name__ == '__main__':
    unittest.main()
