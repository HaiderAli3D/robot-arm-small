"""Pure neutral-relative robot-arm mapping and fail-closed tracking state."""

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


def _circular_mean(values: list[float]) -> float:
    return math.degrees(math.atan2(sum(math.sin(math.radians(x)) for x in values),
                                   sum(math.cos(math.radians(x)) for x in values)))


class Controller:
    """Map GPIO6/7/8 around nominal 90 and GPIO9 around claw_open.

    Claw target is open + direction * gain * closure * (closed - open),
    clamped to configured joint bounds. Closure is 0 at calibrated open
    pinch and 1 at pinch_closed_ratio; reversing direction reverses travel.

    Calibration requires <=8-degree excursion from its first sample on each
    angular channel and <=0.12 pinch-ratio excursion, with elbow and wrist
    within 20 degrees of straight and pinch >0.4 for the configured duration.
    Neither calibration nor tracking reacquisition automatically resumes.
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
        """Synchronize paused outputs after a firmware hold without recalibration."""
        if self.active:
            raise ValueError("pause before synchronizing held device outputs")
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)

    def reset(self, angles=(90, 90, 90, 90)) -> None:
        """Forget calibration and synchronize with actual held device outputs."""
        self._angles = self._checked_angles(angles)
        self._filtered = list(self._angles)
        self.calibrated = False
        self.active = False
        self.status = "Calibrate with straight right arm and wrist, open hand"
        self._calibrating = False
        self._calibration_ready_at = None
        self._samples = []
        self._reference = None
        self._last_update = None
        self._last_valid = None
        self._current = (None, None, None, None)
        self._loss_since = None

    @staticmethod
    def _time(now: float) -> None:
        if not math.isfinite(now):
            raise ValueError("time must be finite")

    def begin_calibration(self, now: float, delay: float = 0.0) -> None:
        self._time(now)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("calibration delay must be finite and nonnegative")
        self.pause("Hold neutral pose steady to calibrate")
        self.calibrated = False
        self._reference = None
        self._calibrating = True
        self._samples = []
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
        if (not self.calibrated or self._last_valid is None
                or not all(v is not None for v in self._current)
                or now < self._last_valid
                or now - self._last_valid >= self.config.loss_timeout - 1e-9):
            self.pause("Resume needs calibration and fresh tracking of both hands")
            return False
        self.active = True
        self.status = "Tracking"
        self._last_update = now
        self._filtered = list(self._angles)
        self._loss_since = None
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
        if (any(v is None for v in values) or abs(values[1]) > 20
                or abs(_relative(values[2], 0)) > 20
                or values[3] <= max(0.4, self.config.pinch_closed_ratio)):
            self._samples = []
            self.status = "Calibration needs straight right arm and wrist, open hand, both hands visible"
            return
        if self._samples:
            anchor = self._samples[0][1]
            stable = (abs(_relative(values[0], anchor[0])) <= 8
                      and abs(values[1] - anchor[1]) <= 8
                      and abs(_relative(values[2], anchor[2])) <= 8
                      and abs(values[3] - anchor[3]) <= 0.12)
            if not stable:
                self._samples = []
        self._samples.append((now, values))
        elapsed = now - self._samples[0][0]
        self.status = "Hold neutral pose steady to calibrate"
        if elapsed + 1e-9 < self.config.calibration_seconds:
            return
        columns = list(zip(*(sample for _, sample in self._samples)))
        self._reference = (_circular_mean(columns[0]), sum(columns[1]) / len(columns[1]),
                           _circular_mean(columns[2]), sum(columns[3]) / len(columns[3]))
        self.calibrated = True
        self._calibrating = False
        self._samples = []
        self.status = "Calibrated; resume to move"

    def update(self, observation: Observation, now: float) -> tuple[float, ...]:
        self._time(now)
        dt = 0.0 if self._last_update is None else now - self._last_update
        self._last_update = now
        if dt < 0 or dt >= self.config.loss_timeout - 1e-9:
            self.pause("Tracking frame gap; resume to move")
            self._samples = []
        values = self._values(observation)
        self._current = values
        complete = all(v is not None for v in values)
        if self._loss_since is not None and now - self._loss_since >= self.config.loss_timeout - 1e-9:
            self.pause("Tracking lost; reacquire both hands and resume")
        if complete:
            self._last_valid = now
            self._loss_since = None
        elif self._loss_since is None:
            self._loss_since = now
        if self._calibrating:
            self._calibrate(values, now)
            return self.angles
        if not self.active:
            return self.angles
        self.status = "Tracking" if complete else "Missing tracking; affected joints held"
        alpha = 1.0 if self.config.smoothing_tau == 0 else -math.expm1(-dt / self.config.smoothing_tau)
        for i, value in enumerate(values):
            if value is None:
                self._filtered[i] = self._angles[i]
                continue
            joint = self.config.joints[i]
            if i == 3:
                closure = (self._reference[3] - value) / (self._reference[3] - self.config.pinch_closed_ratio)
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
            step = self._filtered[i] - self._angles[i]
            limit = self.config.max_speed * max(0.0, dt)
            self._angles[i] += max(-limit, min(limit, step))
        return self.angles
