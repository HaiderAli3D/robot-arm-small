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
        self.control_mode = 'tracking'

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
        self.control_mode = 'tracking'
        self.controller.begin_calibration(now, delay=4.0)

    def use_tracking(self, now):
        self.control_mode = 'tracking'
        if self.controller.active:
            self.controller.resume(now)
        else:
            self.controller.status = 'Tracking selected - SPACE to run'

    def nudge(self, pin, delta, now):
        if isinstance(pin, bool) or pin not in range(6,10):
            raise ValueError('servo pin must be GPIO6..GPIO9')
        self.controller.nudge(pin - 6, delta)
        self.control_mode = 'keyboard'
        if not self.controller.active:
            self.resume(now)
        elif self.link and self.connected:
            try:
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)
        self.controller.status = f'Keyboard: IO{pin} {self.controller.angles[pin-6]:.0f} degrees - M for tracking'
        self._next_send = now + 1 / self.config.send_hz

    def prepare_camera_switch(self):
        """Camera selection leaves the run latch and reference pose intact."""
        self.controller.status = 'Switching camera - run state retained'

    def resume(self, now):
        self.controller.resume(now, capture_reference=self.control_mode == 'tracking')
        if self.control_mode == 'keyboard':
            self.controller.status = 'Keyboard control - M for tracking'
        if self.link and self.connected:
            try:
                self.link.resume()
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)
        self._next_send = now + 1 / self.config.send_hz
        return True

    def step(self, observation: Observation, now):
        if self.control_mode == 'tracking':
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
