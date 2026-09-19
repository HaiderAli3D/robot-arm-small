"""Convert MediaPipe results to independent, confidence-gated controls.

Inference sees the original frame. Only control-plane x coordinates and the
preview are mirrored. Hand ownership comes from pose wrists, not detection order
or the model's selfie-dependent handedness labels.
"""

import math
from pathlib import Path

from .config import Config
from .control import Observation
from .geometry import Point, angle, associate_hands, clockwise_angle, pinch_ratio, signed_bend


def _finite(point):
    return all(math.isfinite(getattr(point, axis)) for axis in ('x', 'y', 'z'))


def _visible(point, confidence):
    presence = getattr(point, 'presence', None)
    visibility = getattr(point, 'visibility', None)
    return (_finite(point) and 0 <= point.x <= 1 and 0 <= point.y <= 1
            and visibility is not None and visibility >= confidence
            and (presence is None or presence >= confidence))


def observation_from_results(pose_result, hand_result, width, height, confidence=.6):
    """Return (Observation, anatomical side -> original hand result index)."""
    empty = Observation(None, None, None, None)
    if width <= 0 or height <= 0 or not pose_result.pose_landmarks:
        return empty, {}
    pose = pose_result.pose_landmarks[0]
    if len(pose) < 33:
        return empty, {}
    diagonal = math.hypot(width, height)

    def pixel(p):
        return Point(p.x * width, p.y * height)

    def normalized(p):
        return Point(p.x * width / diagonal, p.y * height / diagonal)

    wrists = {side: normalized(pose[index]) for side, index in (('left', 15), ('right', 16))
              if _visible(pose[index], confidence)}
    valid = []
    for index, hand in enumerate(hand_result.hand_landmarks):
        categories = hand_result.handedness[index] if index < len(hand_result.handedness) else []
        if (len(hand) == 21 and categories and categories[0].score >= confidence
                and all(_finite(p) and 0 <= p.x <= 1 and 0 <= p.y <= 1 for p in hand)):
            valid.append(index)
    assignment = associate_hands(wrists, [normalized(hand_result.hand_landmarks[i][0]) for i in valid],
                                 max_distance=.12, ambiguity_margin=.035)
    matches = {side: valid[index] for side, index in assignment.items()}
    elbow = wrist = rotation = pinch = None
    if all(_visible(pose[i], confidence) for i in (12, 14, 16)) and pose_result.pose_world_landmarks:
        world = pose_result.pose_world_landmarks[0]
        if len(world) >= 17 and all(_finite(world[i]) for i in (12, 14, 16)):
            interior = angle(*(Point(world[i].x, world[i].y, world[i].z) for i in (12, 14, 16)))
            elbow = None if interior is None else 180 - interior
    if 'right' in matches:
        hand = [pixel(p) for p in hand_result.hand_landmarks[matches['right']]]
        # An edge-on or tiny palm is unreliable for pinch normalization.
        if math.hypot(hand[5].x-hand[17].x, hand[5].y-hand[17].y) >= .01 * diagonal:
            pinch = pinch_ratio(hand[4], hand[8], hand[5], hand[17])
        if all(_visible(pose[i], confidence) for i in (14, 16)):
            forearm = Point((pose[16].x-pose[14].x)*width, (pose[16].y-pose[14].y)*height)
            direction = Point(hand[9].x-hand[0].x, hand[9].y-hand[0].y)
            if math.hypot(direction.x, direction.y) >= .015 * diagonal:
                wrist = signed_bend(-forearm.x, forearm.y, -direction.x, direction.y)
    if 'left' in matches:
        hand = [pixel(p) for p in hand_result.hand_landmarks[matches['left']]]
        dx, dy = hand[9].x-hand[0].x, hand[9].y-hand[0].y
        if math.hypot(dx, dy) >= .015 * diagonal:
            rotation = clockwise_angle(-dx, dy)
    return Observation(rotation, elbow, wrist, pinch), matches


class Tracker:
    """Synchronous same-frame pose + hand inference with monotonic VIDEO times."""

    def __init__(self, config: Config, models: Path):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        from .models import check_models

        check_models(models)
        self.mp = mp
        self.config = config
        self._last_ms = -1
        self.pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(models / 'pose_landmarker_lite.task')),
            running_mode=vision.RunningMode.VIDEO, num_poses=1,
            min_pose_detection_confidence=config.confidence,
            min_pose_presence_confidence=config.confidence, min_tracking_confidence=config.confidence))
        try:
            self.hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(models / 'hand_landmarker.task')),
                running_mode=vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=config.confidence,
                min_hand_presence_confidence=config.confidence, min_tracking_confidence=config.confidence))
        except Exception:
            self.pose.close()
            raise

    def process(self, frame, captured_at):
        import cv2
        timestamp = max(self._last_ms + 1, int(captured_at * 1000))
        self._last_ms = timestamp
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        pose = self.pose.detect_for_video(image, timestamp)
        hands = self.hands.detect_for_video(image, timestamp)
        height, width = frame.shape[:2]
        observation, matches = observation_from_results(pose, hands, width, height, self.config.confidence)
        return observation, matches, pose, hands

    def close(self):
        self.hands.close()
        self.pose.close()
