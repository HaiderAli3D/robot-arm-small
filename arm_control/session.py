"""Coordinate calibrated tracking with the firmware's held output state."""

from .config import Config
from .control import Controller, Observation
from .transport import LinkError


class Session:
    def __init__(self, config: Config, link=None):
        self.config = config
        self.controller = Controller(config)
        self.link = link
        self.connected = link is None
        self.connection_status = 'Preview only - no servo connection' if link is None else 'Disconnected; R to connect'
        self._next_send = 0.0
        self._last_capture = None

    def _fault(self, error):
        angles = self.controller.angles
        self.controller.reset(angles)
        self.connected = False
        self.connection_status = f'{error}; R to reconnect, then C to calibrate'
        if self.link:
            self.link.close()

    def connect(self):
        if self.link is None:
            return
        self.controller.pause()
        try:
            if self.connected:
                self.link.close()
            self.controller.reset(self.link.connect())
            self._last_capture = None
            self.connected = True
            self.connection_status = f'Connected: {self.link.port}' if hasattr(self.link, 'port') else 'Connected'
        except LinkError as error:
            self._fault(error)

    def _hold(self):
        if self.link and self.connected:
            try:
                self.controller.sync_angles(self.link.hold())
            except LinkError as error:
                self._fault(error)

    def pause(self, reason='Paused; Space to resume'):
        self.controller.pause(reason)
        self._hold()

    def calibrate(self, now):
        self.pause()
        if self.connected:
            self.controller.begin_calibration(now)

    def prepare_camera_switch(self):
        """Hold before opening another camera; its coordinate reference is new."""
        self.pause('Switching camera')
        self.controller.reset(self.controller.angles)
        self._last_capture = None

    def resume(self, now):
        if not self.connected or not self.controller.resume(now):
            return False
        if self.link:
            try:
                self.link.resume()
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)
                return False
        self._next_send = now + 1 / self.config.send_hz
        return True

    def step(self, observation: Observation, now):
        active = self.controller.active
        self.controller.update(observation, now)
        if active and not self.controller.active:
            self._hold()
        if self.controller.active and now >= self._next_send:
            if self.link:
                try:
                    self.link.send_pose(self.controller.angles)
                except LinkError as error:
                    self._fault(error)
            # Drop missed send slots instead of queuing stale targets.
            self._next_send = now + 1 / self.config.send_hz
        return self.controller.angles

    def frame(self, observation: Observation, captured_at, now):
        """Use capture time, not UI polling time, for the camera watchdog."""
        gap = self._last_capture is not None and captured_at-self._last_capture >= self.config.loss_timeout - 1e-9
        stale = now-captured_at >= self.config.loss_timeout - 1e-9
        self._last_capture = captured_at
        if (gap or stale) and self.controller.active:
            self.pause('Camera frame gap; Space to resume with fresh tracking')
        return self.step(Observation(None,None,None,None) if stale else observation, now)

    def camera_missing(self, now):
        if (self._last_capture is not None and now-self._last_capture >= self.config.loss_timeout - 1e-9
                and self.controller.active):
            self.pause('Camera frame gap; Space to resume with fresh tracking')
        return self.step(Observation(None,None,None,None), now)

    def close(self):
        self.controller.pause('Stopped')
        if self.link:
            self.link.close()
        self.connected = False
