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

    def _fault(self, error):
        self.connected = False
        self.connection_status = f'{error}; R to reconnect (run state retained)'
        if self.link:
            self.link.close()

    def connect(self):
        if self.link is None:
            return
        try:
            if self.connected:
                self.link.close()
            self.controller.sync_angles(self.link.connect())
            self.connected = True
            self.connection_status = f'Connected: {self.link.port}' if hasattr(self.link, 'port') else 'Connected'
            if self.controller.active:
                self.link.resume()
                self.link.send_pose(self.controller.angles)
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
        self.controller.begin_calibration(now, delay=4.0)

    def prepare_camera_switch(self):
        """Camera selection leaves the run latch and reference pose intact."""
        self.controller.status = 'Switching camera - run state retained'

    def resume(self, now):
        self.controller.resume(now)
        if self.link and self.connected:
            try:
                self.link.resume()
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)
        self._next_send = now + 1 / self.config.send_hz
        return True

    def step(self, observation: Observation, now):
        self.controller.update(observation, now)
        if self.controller.active and now >= self._next_send:
            if self.link and self.connected:
                try:
                    self.link.send_pose(self.controller.angles)
                except LinkError as error:
                    self._fault(error)
            # Drop missed send slots instead of queuing stale targets.
            self._next_send = now + 1 / self.config.send_hz
        return self.controller.angles

    def frame(self, observation: Observation, captured_at, now):
        """Apply the available observation without changing run state."""
        return self.step(observation, now)

    def camera_missing(self, now):
        return self.step(Observation(None,None,None,None), now)

    def close(self):
        self.controller.pause('Stopped')
        if self.link:
            self.link.close()
        self.connected = False
