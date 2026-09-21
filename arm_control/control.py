"""Neutral-relative robot-arm mapping with a user-controlled run/pause latch."""

from dataclasses import dataclass
import math
from numbers import Real

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
    """Map rotation/elbow/wrist to GPIO6/7/8 and pinch to GPIO9.

    Calibration snapshots any complete tracked pose and the current servo
    commands after the countdown. Every output then moves relative to its
    captured position; calibration itself never recentres the robot.
    Pinch uses the change in normalized closure, scaled by the configured
    open/closed span and gain, without joint travel clipping.
    Tracking loss and calibration never change the user's run/pause state.
    """

    def __init__(self, config: Config):
        self.config = config
        self.reset()

    @property
    def angles(self) -> tuple[float, ...]:
        return tuple(self._angles)

    @property
    def positions(self) -> tuple[float, ...]:
        """Signed positions relative to the most recently captured servo zeros."""
        return tuple(angle - zero for angle, zero in zip(self._angles,self._zero_angles))

    @property
    def zero_angles(self) -> tuple[float, ...]:
        """Raw protocol angles represented by displayed zero on each servo."""
        return self._zero_angles

    @property
    def calibrating(self) -> bool:
        return self._calibrating

    @staticmethod
    def _checked_angles(angles) -> list[float]:
        if len(angles) != 4 or not all(
            not isinstance(v, bool) and isinstance(v, Real)
            and -(2**31) <= v <= 2**31 - 1 and math.isfinite(v) for v in angles
        ):
            raise ValueError("requires four finite device angles representable as signed 32-bit values")
        return [float(v) for v in angles]

    def sync_angles(self, angles) -> None:
        """Synchronize device outputs without changing calibration or run state."""
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)

    def zero_current_positions(self) -> None:
        """Save commanded positions as display zeros without moving outputs."""
        self._zero_angles = tuple(self._angles)

    def reset(self, angles=(90, 90, 90, 90)) -> None:
        """Forget calibration and synchronize with actual held device outputs."""
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)
        self._zero_angles = (90.0,) * 4
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

    def resume(self, now: float, *, capture_reference: bool = True) -> bool:
        self._time(now)
        if capture_reference and not self.calibrated and not self._calibrating:
            self.begin_calibration(now)
        self.active = True
        self.status = "Running" if self.calibrated else "Running - waiting for a tracked reference pose"
        self._last_update = now
        self._filtered = list(self._angles)
        return True

    def nudge(self, index: int, delta: float) -> None:
        """Set one servo directly, independently of tracking gain/reference."""
        if isinstance(index, bool) or index not in range(4):
            raise ValueError('servo index must be 0..3')
        if not math.isfinite(delta):
            raise ValueError('servo increment must be finite')
        angles = list(self.angles)
        angles[index] += delta
        self.sync_angles(angles)
        self._calibrating = False

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
        self._reference = values
        self._zero_angles = tuple(self._angles)
        self._filtered = list(self._angles)
        self.calibrated = True
        self._calibrating = False
        self.status = "Current positions zeroed - running" if self.active else "Current positions zeroed - SPACE to start"

    def _closure(self, pinch: float) -> float:
        closure = ((self.config.pinch_open_ratio - pinch)
                   / (self.config.pinch_open_ratio - self.config.pinch_closed_ratio))
        return max(0.0,min(1.0,closure))

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
        unencodable = []
        # Observations are rotation/elbow/wrist/pinch; servo pins are
        # GPIO6 rotation, GPIO7 elbow, GPIO8 wrist, GPIO9 claw.
        for i, source in enumerate((0, 1, 2, 3)):
            value = values[source]
            if value is None:
                self._filtered[i] = self._angles[i]
                continue
            joint = self.config.joints[i]
            if i == 3:
                closure_change = self._closure(value) - self._closure(self._reference[3])
                target = (self._zero_angles[i] + joint.direction * joint.gain * closure_change
                          * (self.config.claw_closed - self.config.claw_open))
            else:
                relative = (value - self._reference[source] if source == 1
                            else _relative(value, self._reference[source]))
                target = self._zero_angles[i] + joint.direction * joint.gain * relative
            # Protocol representation only: do not corrupt a valid output or
            # disconnect the other channels when a numeric target cannot encode.
            if not -(2**31) <= target <= 2**31 - 1:
                self._filtered[i] = self._angles[i]
                unencodable.append(f'IO{i+6}')
                continue
            if abs(target - self._angles[i]) <= self.config.deadband:
                self._filtered[i] = self._angles[i]
                continue
            self._filtered[i] += alpha * (target - self._filtered[i])
            self._angles[i] = self._filtered[i]
        if unencodable:
            self.status = ('Running - ' + ', '.join(unencodable)
                           + ' exceeds protocol integer range; target unchanged')
        return self.angles
