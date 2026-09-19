"""Camera scheduling tests with controlled external capture streams; no hardware."""

import queue
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from arm_control.camera import Camera, CapturedFrame


class CaptureStream:
    def __init__(self):
        self.frames = queue.Queue()
        self.reads = 0
        self.condition = threading.Condition()
        self.released = threading.Event()
        self.owner = None
        self.release_thread = None

    def read(self):
        with self.condition:
            self.owner = threading.get_ident()
            self.reads += 1
            self.condition.notify_all()
        item = self.frames.get()
        if isinstance(item, Exception):
            raise item
        return item

    def release(self):
        self.release_thread = threading.get_ident()
        self.released.set()

    def wait_reads(self, count):
        with self.condition:
            return self.condition.wait_for(lambda: self.reads >= count, timeout=1)


class CameraTests(unittest.TestCase):
    def make_camera(self, clock=lambda: 123.5):
        stream = CaptureStream()
        opened = []

        def factory(index, width, height):
            opened.append((index, width, height))
            return stream

        camera = Camera(2, 960, 720, capture_factory=factory, clock=clock)
        self.addCleanup(self.clean_camera, camera, stream)
        return camera, stream, opened

    @staticmethod
    def clean_camera(camera, stream):
        stream.frames.put((False, None))
        camera.close()

    def test_construction_does_not_open_and_start_publishes_timestamped_frame(self):
        camera, stream, opened = self.make_camera()
        self.assertEqual(opened, [])
        self.assertIs(camera.start(), camera)
        image = object()
        stream.frames.put((True, image))
        frame = camera.latest(timeout=1)
        self.assertIsInstance(frame, CapturedFrame)
        self.assertEqual(frame.sequence, 1)
        self.assertEqual(frame.captured_at, 123.5)
        self.assertIs(frame.image, image)
        self.assertEqual(opened, [(2, 960, 720)])
        self.assertIsNone(camera.error)

    def test_only_newest_frame_is_retained_without_backlog(self):
        ticks = iter((10.0, 11.0, 12.0))
        camera, stream, _ = self.make_camera(clock=lambda: next(ticks))
        camera.start()
        stream.frames.put((True, "first"))
        stream.frames.put((True, "second"))
        stream.frames.put((True, "third"))
        self.assertTrue(stream.wait_reads(4))
        frame = camera.latest(timeout=0)
        self.assertEqual((frame.sequence, frame.image, frame.captured_at), (3, "third", 12.0))
        self.assertIsNone(camera.latest(after=3, timeout=0))

    def test_latest_waits_for_a_newer_sequence_and_has_a_finite_timeout(self):
        camera, stream, _ = self.make_camera()
        camera.start()
        stream.frames.put((True, "first"))
        first = camera.latest(timeout=1)
        start = time.monotonic()
        self.assertIsNone(camera.latest(after=first.sequence, timeout=0.03))
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.02)
        self.assertLess(elapsed, 0.3)
        stream.frames.put((True, "second"))
        self.assertEqual(camera.latest(after=first.sequence, timeout=1).image, "second")

    def test_capture_failure_sets_error_releases_and_wakes_waiters(self):
        camera, stream, _ = self.make_camera()
        camera.start()
        stream.frames.put((False, None))
        start = time.monotonic()
        self.assertIsNone(camera.latest(timeout=1))
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertIsNotNone(camera.error)
        self.assertTrue(stream.released.wait(1))
        self.assertEqual(stream.release_thread, stream.owner)

    def test_capture_exception_is_available_to_gui(self):
        camera, stream, _ = self.make_camera()
        camera.start()
        stream.frames.put(OSError("driver disconnected"))
        self.assertIsNone(camera.latest(timeout=1))
        self.assertIn("driver disconnected", camera.error)
        self.assertTrue(stream.released.wait(1))

    def test_open_failure_is_reported_without_raising_in_gui_thread(self):
        def failing_factory(index, width, height):
            raise OSError("device unavailable")

        camera = Camera(0, 640, 480, capture_factory=failing_factory)
        self.addCleanup(camera.close)
        camera.start()
        self.assertIsNone(camera.latest(timeout=1))
        self.assertIn("device unavailable", camera.error)

    def test_close_is_bounded_and_does_not_release_during_blocked_read(self):
        camera, stream, _ = self.make_camera()
        camera.start()
        self.assertTrue(stream.wait_reads(1))
        start = time.monotonic()
        camera.close()
        self.assertLess(time.monotonic() - start, 0.6)
        self.assertFalse(stream.released.is_set())
        self.assertIsNone(camera.latest(timeout=1))
        stream.frames.put((True, "late frame"))
        self.assertTrue(stream.released.wait(1))
        self.assertEqual(stream.release_thread, stream.owner)
        self.assertIsNone(camera.latest(timeout=0))
        self.assertIsNone(camera.error)
        camera.close()

    def test_bad_latest_timeout_cannot_create_an_infinite_wait(self):
        camera, _, _ = self.make_camera()
        for timeout in (-1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    camera.latest(timeout=timeout)

    def test_windows_falls_back_from_dshow_and_sets_capture_properties(self):
        stream = CaptureStream()
        properties = []
        stream.isOpened = lambda: True
        stream.set = lambda key, value: properties.append((key, value)) or True
        rejected = SimpleNamespace(isOpened=lambda: False, release=lambda: releases.append("dshow"))
        attempts = []
        releases = []

        def open_capture(index, backend):
            attempts.append((index, backend))
            return rejected if backend == 700 else stream

        fake_cv2 = SimpleNamespace(VideoCapture=open_capture, CAP_DSHOW=700,
                                   CAP_MSMF=1400, CAP_ANY=0, CAP_PROP_FRAME_WIDTH=3,
                                   CAP_PROP_FRAME_HEIGHT=4, CAP_PROP_FPS=5,
                                   CAP_PROP_BUFFERSIZE=38)
        camera = Camera(1, 960, 720)
        self.addCleanup(self.clean_camera, camera, stream)
        with patch.dict(sys.modules, {"cv2": fake_cv2}), patch("arm_control.camera.sys.platform", "win32"):
            camera.start()
            self.assertTrue(stream.wait_reads(1))
        self.assertEqual(attempts, [(1, 700), (1, 1400)])
        self.assertEqual(releases, ["dshow"])
        self.assertEqual(properties, [(3, 960), (4, 720), (5, 30), (38, 1)])


if __name__ == "__main__":
    unittest.main()
