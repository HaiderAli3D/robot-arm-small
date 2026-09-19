"""Camera selection tests with fake camera boundaries; no device access."""

import unittest

from arm_control.camera import CapturedFrame
from arm_control.camera_switch import CameraSwitcher


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class FakeCamera:
    def __init__(self, index):
        self.index = index
        self.error = None
        self.frame = None
        self.start_calls = 0
        self.close_calls = 0
        self.start_error = None

    def start(self):
        self.start_calls += 1
        if self.start_error:
            raise self.start_error
        return self

    def latest(self, after=-1, timeout=0.05):
        if timeout != 0:
            raise AssertionError("Camera switching must never wait for a frame")
        return self.frame

    def close(self):
        self.close_calls += 1


class CameraSwitcherTests(unittest.TestCase):
    def make_switcher(self, initial=0, timeout=3.0):
        clock = Clock()
        original = FakeCamera(initial)
        created = []

        def factory(index, width, height):
            self.assertEqual((width, height), (960, 720))
            candidate = FakeCamera(index)
            created.append(candidate)
            return candidate

        switcher = CameraSwitcher(original, initial, 960, 720,
                                  camera_factory=factory, clock=clock, probe_timeout=timeout)
        return switcher, original, created, clock

    def test_constructor_keeps_current_camera_and_does_not_open_another(self):
        switcher, original, created, _ = self.make_switcher()
        self.assertIs(switcher.camera, original)
        self.assertEqual(switcher.index, 0)
        self.assertFalse(switcher.switching)
        self.assertEqual(created, [])
        self.assertFalse(switcher.poll())

    def test_switch_waits_for_fresh_frame_then_replaces_camera_exactly_once(self):
        switcher, original, created, clock = self.make_switcher()
        self.assertTrue(switcher.request_next())
        candidate = created[0]
        self.assertEqual((candidate.index, candidate.start_calls), (1, 1))
        self.assertTrue(switcher.switching)
        self.assertFalse(switcher.poll())
        self.assertIs(switcher.camera, original)
        self.assertEqual(original.close_calls, 0)
        candidate.frame = CapturedFrame(1, clock(), object())
        self.assertTrue(switcher.poll())
        self.assertIs(switcher.camera, candidate)
        self.assertEqual(switcher.index, 1)
        self.assertEqual(original.close_calls, 1)
        self.assertFalse(switcher.switching)
        self.assertFalse(switcher.poll())
        self.assertEqual(original.close_calls, 1)

    def test_cycles_indices_after_the_selected_camera(self):
        switcher, _, created, clock = self.make_switcher(initial=2)
        switcher.request_next()
        self.assertEqual(created[-1].index, 3)
        created[-1].frame = CapturedFrame(1, clock(), object())
        self.assertTrue(switcher.poll())
        switcher.request_next()
        self.assertEqual(created[-1].index, 0)

    def test_initial_index_outside_default_range_remains_in_cycle(self):
        switcher, _, created, clock = self.make_switcher(initial=7)
        switcher.request_next()
        self.assertEqual(created[-1].index, 0)
        created[-1].frame = CapturedFrame(1, clock(), object())
        switcher.poll()
        switcher.request_next()
        for expected in (1, 2, 3):
            self.assertEqual(created[-1].index, expected)
            created[-1].error = "unavailable"
            self.assertFalse(switcher.poll())
        self.assertEqual(created[-1].index, 7)

    def test_unavailable_candidates_are_closed_and_skipped(self):
        switcher, original, created, clock = self.make_switcher()
        switcher.request_next()
        rejected = created[-1]
        rejected.error = "device missing"
        self.assertFalse(switcher.poll())
        self.assertEqual(rejected.close_calls, 1)
        self.assertEqual(created[-1].index, 2)
        self.assertEqual(original.close_calls, 0)
        created[-1].frame = CapturedFrame(1, clock(), object())
        self.assertTrue(switcher.poll())
        self.assertEqual(rejected.close_calls, 1)

    def test_timeouts_exhaust_scan_and_retain_usable_original(self):
        switcher, original, created, clock = self.make_switcher()
        switcher.request_next()
        for expected in (1, 2, 3):
            self.assertEqual(created[-1].index, expected)
            clock.now += 3.0
            self.assertFalse(switcher.poll())
        self.assertFalse(switcher.switching)
        self.assertIs(switcher.camera, original)
        self.assertEqual(original.close_calls, 0)
        self.assertEqual([camera.close_calls for camera in created], [1, 1, 1])
        self.assertIn("keeping camera 0", switcher.status.lower())
        self.assertFalse(switcher.poll())
        self.assertEqual(len(created), 3)

    def test_duplicate_click_does_not_restart_or_extend_probe_deadline(self):
        switcher, _, created, clock = self.make_switcher()
        switcher.request_next()
        clock.now += 2.0
        self.assertFalse(switcher.request_next())
        self.assertEqual(len(created), 1)
        clock.now += 1.0
        switcher.poll()
        self.assertEqual(created[-1].index, 2)

    def test_stale_future_and_missing_image_frames_cannot_select_camera(self):
        for timestamp, image in ((99.5, object()), (99.0, object()),
                                 (100.1, object()), (float("nan"), object()), (100.0, None)):
            with self.subTest(timestamp=timestamp, image=image):
                switcher, original, created, clock = self.make_switcher()
                switcher.request_next()
                created[-1].frame = CapturedFrame(1, timestamp, image)
                self.assertFalse(switcher.poll())
                self.assertIs(switcher.camera, original)
                self.assertTrue(switcher.switching)
                created[-1].frame = CapturedFrame(2, clock(), object())
                self.assertTrue(switcher.poll())

    def test_close_releases_pending_and_current_once_and_prevents_reopen(self):
        switcher, original, created, _ = self.make_switcher()
        switcher.request_next()
        switcher.close()
        switcher.close()
        self.assertEqual(original.close_calls, 1)
        self.assertEqual(created[0].close_calls, 1)
        self.assertFalse(switcher.switching)
        self.assertFalse(switcher.request_next())
        self.assertFalse(switcher.poll())
        self.assertEqual(len(created), 1)

    def test_close_after_success_does_not_close_previous_camera_twice(self):
        switcher, original, created, clock = self.make_switcher()
        switcher.request_next()
        created[-1].frame = CapturedFrame(1, clock(), object())
        switcher.poll()
        switcher.close()
        switcher.close()
        self.assertEqual(original.close_calls, 1)
        self.assertEqual(created[-1].close_calls, 1)

    def test_invalid_probe_timeout_is_rejected(self):
        for timeout in (0, -1, float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.make_switcher(timeout=timeout)

    def test_factory_and_start_errors_do_not_abandon_current_camera(self):
        original = FakeCamera(0)
        created = []

        def factory(index, width, height):
            if index == 2:
                raise OSError("camera creation failed")
            camera = FakeCamera(index)
            created.append(camera)
            if index == 1:
                camera.start_error = OSError("camera start failed")
            else:
                camera.frame = CapturedFrame(1, 100.0, object())
            return camera

        switcher = CameraSwitcher(original, 0, 960, 720, camera_factory=factory, clock=lambda: 100.0)
        self.assertTrue(switcher.request_next())
        self.assertEqual(created[0].close_calls, 1)
        self.assertFalse(switcher.poll())  # Index 2 fails construction.
        self.assertFalse(switcher.poll())  # Index 3 starts without waiting.
        self.assertEqual(original.close_calls, 0)
        self.assertTrue(switcher.poll())
        self.assertEqual(switcher.index, 3)
        self.assertEqual(created[0].close_calls, 1)
        self.assertEqual(original.close_calls, 1)

    def test_candidate_error_or_expired_probe_cannot_select_a_fresh_frame(self):
        for failure in ("driver", "timeout"):
            with self.subTest(failure=failure):
                switcher, original, created, clock = self.make_switcher()
                switcher.request_next()
                candidate = created[-1]
                if failure == "driver":
                    candidate.error = "driver disconnected"
                else:
                    clock.now += 3.0
                candidate.frame = CapturedFrame(1, clock(), object())
                self.assertFalse(switcher.poll())
                self.assertIs(switcher.camera, original)
                self.assertEqual(candidate.close_calls, 1)
                self.assertEqual(created[-1].index, 2)


if __name__ == "__main__":
    unittest.main()
