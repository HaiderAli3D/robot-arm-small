from types import SimpleNamespace as NS
import math
import unittest
from unittest.mock import Mock

from arm_control.vision import Tracker, observation_from_results


def point(x, y, z=0, visibility=1, presence=1):
    return NS(x=x, y=y, z=z, visibility=visibility, presence=presence)


def fixture():
    landmarks = [point(0.5, 0.5) for _ in range(33)]
    landmarks[12], landmarks[14], landmarks[16] = point(.3, .5), point(.5, .5), point(.7, .5)
    landmarks[15] = point(.2, .5)
    hands = []
    for x in (.7, .2):
        hand = [point(x, .5) for _ in range(21)]
        hand[5], hand[17] = point(x-.03, .4), point(x+.03, .4)
        hand[4], hand[8] = point(x-.03, .3), point(x+.03, .3)
        hand[9] = point(x+.1, .5) if x == .7 else point(x, .35)
        hands.append(hand)
    pose = NS(pose_landmarks=[landmarks], pose_world_landmarks=[landmarks])
    hand_result = NS(hand_landmarks=hands, handedness=[[NS(score=.99)], [NS(score=.99)]])
    return pose, hand_result


class VisionTests(unittest.TestCase):
    def test_tracker_cleanup_is_idempotent(self):
        tracker = Tracker.__new__(Tracker)
        hands, pose = Mock(), Mock()
        tracker.hands, tracker.pose = hands, pose
        tracker.close()
        tracker.close()
        hands.close.assert_called_once_with()
        pose.close.assert_called_once_with()

    def test_tracker_cleanup_releases_pose_even_if_hands_close_fails(self):
        tracker = Tracker.__new__(Tracker)
        hands, pose = Mock(), Mock()
        hands.close.side_effect = RuntimeError('native close failed')
        tracker.hands, tracker.pose = hands, pose
        with self.assertRaisesRegex(RuntimeError,'native close failed'):
            tracker.close()
        tracker.close()
        hands.close.assert_called_once_with()
        pose.close.assert_called_once_with()

    def test_assigns_anatomical_hands_regardless_of_result_order(self):
        pose, hands = fixture()
        obs, matches = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertEqual(matches, {'right': 0, 'left': 1})
        self.assertAlmostEqual(obs.elbow, 0)
        self.assertAlmostEqual(obs.wrist, 0)
        self.assertAlmostEqual(obs.rotation, -90)
        self.assertAlmostEqual(obs.pinch, 1)
        hands.hand_landmarks.reverse()
        obs2, matches = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertEqual(matches, {'right': 1, 'left': 0})
        self.assertEqual(obs2, obs)

    def test_wrist_uses_pixel_aspect_and_mirrored_clockwise_sign(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][9] = point(.75, .6)
        obs, _ = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertAlmostEqual(obs.wrist, -45)

    def test_hidden_elbow_stops_elbow_and_wrist_but_leaves_pinch(self):
        pose, hands = fixture()
        pose.pose_landmarks[0][14].visibility = .1
        obs, _ = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertIsNone(obs.elbow)
        self.assertIsNone(obs.wrist)
        self.assertIsNotNone(obs.pinch)

    def test_missing_pose_never_assigns_hands_by_list_order(self):
        _, hands = fixture()
        obs, matches = observation_from_results(NS(pose_landmarks=[], pose_world_landmarks=[]), hands, 1000, 500, .6)
        self.assertFalse(matches)
        self.assertEqual((obs.rotation, obs.elbow, obs.wrist, obs.pinch), (None,)*4)

    def test_nonfinite_pinch_tip_does_not_discard_wrist_control(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][8].x = math.nan
        obs, matches = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertIn('right', matches)
        self.assertIsNone(obs.pinch)
        self.assertIsNotNone(obs.wrist)

    def test_nonfinite_hand_wrist_cannot_be_assigned(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][0].x = math.nan
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertNotIn('right', matches)
        self.assertIsNone(obs.pinch)
        self.assertIsNone(obs.wrist)

    def test_moderately_visible_pose_wrists_keep_hand_controls(self):
        pose, hands = fixture()
        for index in (12, 14, 15, 16):
            pose.pose_landmarks[0][index].visibility = .45
            pose.pose_landmarks[0][index].presence = .45
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertEqual(matches, {'right': 0, 'left': 1})
        self.assertTrue(all(value is not None for value in
                            (obs.rotation, obs.elbow, obs.wrist, obs.pinch)))

    def test_clear_wrist_match_survives_pose_estimate_offset(self):
        pose, hands = fixture()
        pose.pose_landmarks[0][16].x = .53
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertEqual(matches, {'right': 0, 'left': 1})
        self.assertIsNotNone(obs.wrist)

    def test_ambiguous_overlapping_wrists_are_not_assigned(self):
        pose, hands = fixture()
        pose.pose_landmarks[0][15].x = .7
        _, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertFalse(matches)

    def test_uncertain_handedness_does_not_hide_pose_associated_hand(self):
        pose, hands = fixture()
        hands.handedness[0][0].score = .51
        obs, _ = observation_from_results(pose, hands, 1000, 500, .6)
        self.assertIsNotNone(obs.wrist)
        self.assertIsNotNone(obs.rotation)

    def test_fingertip_just_outside_image_keeps_hand_tracking(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][20].x = 1.02
        obs, matches = observation_from_results(pose,hands,1000,500,.6)
        self.assertIn('right', matches)
        self.assertIsNotNone(obs.wrist)

    def test_unused_fingertip_outside_image_keeps_hand_controls(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][20].x = 1.2
        obs, matches = observation_from_results(pose,hands,1000,500,.6)
        self.assertIn('right', matches)
        self.assertIsNotNone(obs.wrist)
        self.assertIsNotNone(obs.pinch)

    def test_pinch_tip_outside_image_only_drops_pinch(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][8].x = 1.2
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertIn('right', matches)
        self.assertIsNotNone(obs.wrist)
        self.assertIsNone(obs.pinch)

    def test_invalid_middle_knuckle_only_drops_wrist_and_rotation(self):
        pose, hands = fixture()
        for hand in hands.hand_landmarks:
            hand[9].x = math.inf
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertEqual(matches, {'right': 0, 'left': 1})
        self.assertIsNone(obs.wrist)
        self.assertIsNone(obs.rotation)
        self.assertIsNotNone(obs.pinch)
        self.assertIsNotNone(obs.elbow)

    def test_nonfinite_unused_fingertip_does_not_drop_controls(self):
        pose, hands = fixture()
        hands.hand_landmarks[0][20].x = math.nan
        obs, matches = observation_from_results(pose, hands, 1000, 500)
        self.assertIn('right', matches)
        self.assertIsNotNone(obs.wrist)
        self.assertIsNotNone(obs.pinch)


if __name__ == '__main__':
    unittest.main()
