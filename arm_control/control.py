"""Neutral-relative robot-arm mapping with a user-controlled run/pause latch."""

from dataclasses import dataclass
import math

from .config import Config


@dataclass(frozen=True)
class Observation:
    rotation: float | None
    elbow: float | None
    wrist: float | None
    pinch: float | None


def _relative(value: float, reference: float) -> float:
    return (value - reference + 180.0) % 360.0 - 180.0


class Controller:
    """Map GPIO6/7/8 around nominal 90 and GPIO9 around claw_open.

    Claw target is open + direction * gain * closure * (closed - open),
    clamped to configured joint bounds. Closure is 0 at pinch_open_ratio
    and 1 at pinch_closed_ratio; reversing direction reverses travel.

    Calibration snapshots any complete tracked pose after the countdown.
    Only the arm/wrist zero points depend on that pose; pinch is absolute.
    Tracking loss and calibration never change the user's run/pause state.
    """

    def __init__(self, config: Config):
        self.config = config
        self.reset()

    @property
    def angles(self) -> tuple[float, ...]:
        return tuple(self._angles)

    @property
    def calibrating(self) -> bool:
        return self._calibrating

    @staticmethod
    def _checked_angles(angles) -> list[float]:
        if len(angles) != 4 or not all(math.isfinite(v) and 0 <= v <= 180 for v in angles):
            raise ValueError("requires four finite device angles in 0..180")
        return [float(v) for v in angles]

    def sync_angles(self, angles) -> None:
        """Synchronize device outputs without changing calibration or run state."""
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)

    def reset(self, angles=(90, 90, 90, 90)) -> None:
        """Forget calibration and synchronize with actual held device outputs."""
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)
        self.calibrated = False
        self.active = False
        self.status = "SPACE to run; C to set a reference pose"
        self._calibrating = False
        self._calibration_ready_at = None
        self._reference = None
        self._last_update = None

    @staticmethod
    def _time(now: float) -> None:
        if not math.isfinite(now):
            raise ValueError("time must be finite")

    def begin_calibration(self, now: float, delay: float = 0.0) -> None:
        self._time(now)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("calibration delay must be finite and nonnegative")
        self.status = "Show both hands and your right arm - any pose"
        self.calibrated = False
        self._reference = None
        self._calibrating = True
        self._last_update = now
        self._calibration_ready_at = now + delay
        if delay:
            self.status = f"Calibration starts in {math.ceil(delay)} seconds - show both hands"

    def pause(self, reason: str = "Paused") -> None:
        self.active = False
        self._filtered = list(self._angles)
        self.status = reason

    def resume(self, now: float) -> bool:
        self._time(now)
        if not self.calibrated and not self._calibrating:
            self.begin_calibration(now)
        self.active = True
        self.status = "Running" if self.calibrated else "Running - waiting for a tracked reference pose"
        self._last_update = now
        self._filtered = list(self._angles)
        return True

    @staticmethod
    def _values(observation: Observation) -> tuple[float | None, ...]:
        values = [observation.rotation, observation.elbow, observation.wrist, observation.pinch]
        values = [v if v is not None and math.isfinite(v) else None for v in values]
        if values[1] is not None and not 0 <= values[1] <= 180:
            values[1] = None
        if values[3] is not None and values[3] < 0:
            values[3] = None
        return tuple(values)

    def _calibrate(self, values: tuple[float | None, ...], now: float) -> None:
        if now < self._calibration_ready_at:
            remaining = math.ceil(self._calibration_ready_at - now)
            self.status = f"Calibration starts in {remaining} seconds - show both hands"
            return
        missing_help = ('Show your left hand with fingers visible',
                        'Show your right shoulder, elbow and wrist',
                        'Show your right wrist and hand; keep them in view',
                        'Face your right palm toward the camera; show thumb and index')
        problem = next((help_text for value, help_text in zip(values,missing_help)
                        if value is None), None)
        if problem:
            self.status = problem
            return
        self._reference = values[:3]
        self.calibrated = True
        self._calibrating = False
        self.status = "Reference saved - running" if self.active else "Calibrated - press SPACE to start"

    def update(self, observation: Observation, now: float) -> tuple[float, ...]:
        self._time(now)
        dt = 0.0 if self._last_update is None else max(0.0, now - self._last_update)
        self._last_update = now
        values = self._values(observation)
        complete = all(v is not None for v in values)
        if self._calibrating:
            self._calibrate(values, now)
            return self.angles
        if not self.active:
            return self.angles
        self.status = "Running - tracking" if complete else "Running - waiting for missing tracking; last angles held"
        alpha = 1.0 if self.config.smoothing_tau == 0 else -math.expm1(-dt / self.config.smoothing_tau)
        for i, value in enumerate(values):
            if value is None:
                self._filtered[i] = self._angles[i]
                continue
            joint = self.config.joints[i]
            if i == 3:
                closure = ((self.config.pinch_open_ratio - value)
                           / (self.config.pinch_open_ratio - self.config.pinch_closed_ratio))
                closure = max(0.0, min(1.0, closure))
                target = self.config.claw_open + joint.direction * joint.gain * closure * (self.config.claw_closed - self.config.claw_open)
            else:
                relative = value - self._reference[i] if i == 1 else _relative(value, self._reference[i])
                target = 90.0 + joint.direction * joint.gain * relative
            target = max(joint.minimum, min(joint.maximum, target))
            if abs(target - self._angles[i]) <= self.config.deadband:
                self._filtered[i] = self._angles[i]
                continue
            self._filtered[i] += alpha * (target - self._filtered[i])
            self._angles[i] = self._filtered[i]
        return self.angles
