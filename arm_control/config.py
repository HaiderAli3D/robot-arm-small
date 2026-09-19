"""Validated settings shared by the tracking controller and desktop app."""

from dataclasses import dataclass, fields, replace
import math
from pathlib import Path
import tomllib


def _number(name, value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be a number')
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')


@dataclass(frozen=True)
class JointConfig:
    direction: int = 1
    gain: float = 1

    def __post_init__(self):
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError('direction must be -1 or 1')
        _number('gain', self.gain, 0.001, 10)


@dataclass(frozen=True)
class Config:
    joints: tuple[JointConfig, ...] = (JointConfig(),) * 4
    claw_open: float = 90
    claw_closed: float = 0
    pinch_closed_ratio: float = 0.2
    pinch_open_ratio: float = 1.0
    smoothing_tau: float = 0.12
    deadband: float = 1.0
    confidence: float = 0.4
    hand_confidence: float = 0.2
    camera: int = 0
    width: int = 960
    height: int = 720
    send_hz: float = 30.0

    def __post_init__(self):
        if not isinstance(self.joints, tuple) or len(self.joints) != 4 or not all(
            isinstance(joint, JointConfig) for joint in self.joints
        ):
            raise ValueError('joints must contain four JointConfig values in GPIO order')
        _number('claw_open', self.claw_open, 90, 90)
        _number('claw_closed', self.claw_closed, -(2**31), 2**31 - 1)
        claw = self.joints[3]
        target = self.claw_open + claw.direction * claw.gain * (self.claw_closed - self.claw_open)
        _number('claw target after gain/direction', target, -(2**31), 2**31 - 1)
        for name, low, high in (
            ('pinch_closed_ratio', 0, 0.39), ('smoothing_tau', 0, 2),
            ('pinch_open_ratio', 0.01, 10),
            ('deadband', 0, 10),
            ('confidence', 0.1, 1), ('hand_confidence', 0.1, 1), ('send_hz', 5, 30),
        ):
            _number(name, getattr(self, name), low, high)
        if self.pinch_open_ratio <= self.pinch_closed_ratio:
            raise ValueError('pinch_open_ratio must exceed pinch_closed_ratio')
        for name, low, high in (('camera', 0, 100), ('width', 160, 3840), ('height', 120, 2160)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f'{name} must be an integer')
            _number(name, value, low, high)


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    with Path(path).open('rb') as stream:
        data = tomllib.load(stream)
    allowed = {field.name for field in fields(Config)}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f'Unknown settings: {", ".join(sorted(unknown))}')
    joints = data.pop('joints', {})
    if not isinstance(joints, dict):
        raise ValueError('joints must be TOML tables named gpio6 through gpio9')
    if set(joints) - {'gpio6', 'gpio7', 'gpio8', 'gpio9'}:
        raise ValueError('Joint names must be gpio6, gpio7, gpio8, gpio9')
    result = []
    for pin in range(6, 10):
        values = joints.get(f'gpio{pin}', {})
        if not isinstance(values, dict) or set(values) - {field.name for field in fields(JointConfig)}:
            raise ValueError(f'Unknown joint settings for gpio{pin}')
        result.append(replace(JointConfig(), **values))
    return Config(joints=tuple(result), **data)
