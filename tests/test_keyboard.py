import unittest

from arm_control.keyboard import KeyRepeater


class KeyRepeaterTests(unittest.TestCase):
    def setUp(self):
        self.keys = KeyRepeater(repeat_hz=45)

    def test_tap_is_one_step_even_if_released_between_frames(self):
        self.keys.event(0x61, 1, 0)
        self.keys.event(0x61, (1 << 31) | (1 << 30) | 1, .01)
        self.assertEqual(self.keys.poll(.03, set()), {ord('1'): 1})
        self.assertEqual(self.keys.poll(.1, set()), {})

    def test_hold_repeats_at_forty_five_hz_without_an_extra_initial_delay(self):
        self.keys.event(0x62, 1, 0)
        self.assertEqual(self.keys.poll(0, {0x62}), {ord('2'): 1})
        self.assertEqual(self.keys.poll(.022, {0x62}), {})
        self.assertEqual(self.keys.poll(.023, {0x62}), {ord('2'): 1})
        self.assertEqual(self.keys.poll(.123, {0x62}), {ord('2'): 4})

    def test_native_repeat_does_not_add_steps(self):
        self.keys.event(0x62, 1, 0)
        self.keys.poll(0, {0x62})
        for t, expected in ((.01, {}), (.02, {}), (.03, {ord('2'): 1})):
            self.keys.event(0x62, (1 << 30) | 1, t)
            self.assertEqual(self.keys.poll(t, {0x62}), expected)

    def test_physical_release_discards_due_repeats_before_keyup_is_pumped(self):
        self.keys.event(0x62, 1, 0)
        self.keys.poll(0, {0x62})
        self.assertEqual(self.keys.poll(1, set()), {})

    def test_cancel_requires_fresh_keydown(self):
        self.keys.event(0x62, 1, 0)
        self.keys.poll(0, {0x62})
        self.keys.cancel()
        self.keys.event(0x62, (1 << 30) | 1, 1)
        self.assertEqual(self.keys.poll(1, {0x62}), {})
        self.keys.event(0x62, 1, 2)
        self.assertEqual(self.keys.poll(2, {0x62}), {ord('2'): 1})

    def test_focus_loss_drops_pending_taps_and_holds(self):
        self.keys.event(0x62, 1, 0)
        self.assertEqual(self.keys.poll(.1, {0x62}, focused=False), {})
        self.assertEqual(self.keys.poll(1, {0x62}), {})

    def test_top_row_and_numpad_and_multiple_keys(self):
        self.keys.event(ord('4'), 1, 0)
        self.keys.event(0x68, 1, 0)
        self.assertEqual(self.keys.poll(0, {ord('4'), 0x68}), {ord('4'): 1, ord('8'): 1})

    def test_two_short_taps_between_frames_are_both_preserved(self):
        for t in (0, .05):
            self.keys.event(0x61, 1, t)
            self.keys.event(0x61, (1 << 31) | 1, t+.01)
        self.assertEqual(self.keys.poll(.1, set()), {ord('1'): 2})

    def test_camera_stall_does_not_replay_seconds_of_old_repeats(self):
        self.keys.event(0x62, 1, 0)
        self.keys.poll(0, {0x62})
        self.assertEqual(self.keys.poll(5, {0x62}), {})
        self.assertEqual(self.keys.poll(5.023, {0x62}), {ord('2'): 1})
