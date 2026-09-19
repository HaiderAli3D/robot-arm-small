"""Dependency-free landmark geometry; screen y increases downwards."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float = 0.0


def _vector(a: Point, b: Point) -> tuple[float, float, float]:
    return a.x - b.x, a.y - b.y, a.z - b.z


def angle(a: Point, b: Point, c: Point) -> float | None:
    """Unsigned 3-D interior angle ABC, or None for unusable points."""
    u, v = _vector(a, b), _vector(c, b)
    if not all(math.isfinite(x) for x in (*u, *v)):
        return None
    scale = math.hypot(*u) * math.hypot(*v)
    if scale <= 1e-12:
        return None
    cosine = sum(x * y for x, y in zip(u, v)) / scale
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def clockwise_angle(vector_x: float, vector_y: float) -> float | None:
    """Clockwise direction in screen coordinates, in [-180, 180]."""
    if not all(math.isfinite(x) for x in (vector_x, vector_y)):
        return None
    if math.hypot(vector_x, vector_y) <= 1e-12:
        return None
    return math.degrees(math.atan2(vector_y, vector_x))


def signed_bend(forearm_x: float, forearm_y: float, hand_x: float, hand_y: float) -> float | None:
    """Shortest clockwise bend from outward forearm to outward hand."""
    forearm = clockwise_angle(forearm_x, forearm_y)
    hand = clockwise_angle(hand_x, hand_y)
    if forearm is None or hand is None:
        return None
    return (hand - forearm + 180.0) % 360.0 - 180.0


def pinch_ratio(thumb: Point, index: Point, palm_index: Point, palm_pinky: Point) -> float | None:
    """Thumb/index separation divided by palm width in supplied coordinates."""
    tip, palm = _vector(thumb, index), _vector(palm_index, palm_pinky)
    if not all(math.isfinite(x) for x in (*tip, *palm)):
        return None
    width = math.hypot(*palm)
    if width <= 1e-12:
        return None
    return math.hypot(*tip) / width


def associate_hands(pose_wrists: dict[str, Point], hand_wrists: list[Point],
                    max_distance: float, ambiguity_margin: float) -> dict[str, int]:
    """Conservative mutual-nearest association in diagonal-normalized image xy.

    A match must be distinctly nearest from both the pose and hand side.
    Ambiguous crossings are omitted instead of guessing anatomical identity.
    """
    if not math.isfinite(max_distance) or max_distance < 0:
        raise ValueError("max_distance must be finite and nonnegative")
    if not math.isfinite(ambiguity_margin) or ambiguity_margin < 0:
        raise ValueError("ambiguity_margin must be finite and nonnegative")
    distances = {}
    for side, pose in pose_wrists.items():
        for index, hand in enumerate(hand_wrists):
            if all(math.isfinite(v) for v in (pose.x, pose.y, hand.x, hand.y)):
                distances[side, index] = math.hypot(pose.x - hand.x, pose.y - hand.y)
    result = {}
    for side in pose_wrists:
        candidates = sorted((distance, index) for (name, index), distance in distances.items()
                            if name == side and distance <= max_distance)
        if not candidates:
            continue
        distance, index = candidates[0]
        if len(candidates) > 1 and candidates[1][0] - distance <= ambiguity_margin:
            continue
        competitors = sorted(d for (name, i), d in distances.items()
                             if i == index and name != side and d <= max_distance)
        if competitors and competitors[0] - distance <= ambiguity_margin:
            continue
        result[side] = index
    return result
