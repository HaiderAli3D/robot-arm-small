"""Coordinate calibrated tracking with the firmware's held output state."""

from numbers import Real

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
        self._release_until = None

    @property
    def servos_released(self):
        return self._release_until is not None

    def _restore_outputs(self):
        if self.link and self.connected:
            try:
                self.link.resume()
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)

    def tick(self, now):
        """End the output-release countdown even without camera observations."""
        if self.servos_released and now >= self._release_until:
            self._release_until = None
            self._restore_outputs()
            self._next_send = now + 1 / self.config.send_hz

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
            if self.servos_released:
                self.link.off()
            elif self.controller.active:
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
        self._release_until = now + 4.0
        if self.link and self.connected:
            try:
                self.link.off()
            except LinkError as error:
                self._fault(error)

    def use_tracking(self, now):
        self.control_mode = 'tracking'
        if self.controller.active:
            self.controller.resume(now)
        else:
            self.controller.status = 'Tracking selected - SPACE to run'

    def nudge(self, pin, delta, now):
        if isinstance(pin, bool) or not isinstance(pin, int) or pin not in range(6,10):
            raise ValueError('servo pin must be GPIO6..GPIO9')
        self.controller.nudge(pin - 6, delta)
        self.control_mode = 'keyboard'
        released = self.servos_released
        self._release_until = None
        if not self.controller.active:
            self.resume(now)
        elif released:
            self._restore_outputs()
        elif self.link and self.connected:
            try:
                self.link.send_pose(self.controller.angles)
            except LinkError as error:
                self._fault(error)
        self.controller.status = f'Keyboard: IO{pin} {self.controller.positions[pin-6]:.0f} degrees - M for tracking'
        self._next_send = now + 1 / self.config.send_hz

    def set_position(self, pin, position, now):
        """Select a signed position about this servo's saved calibration zero."""
        if isinstance(pin, bool) or not isinstance(pin, int) or pin not in range(6,10):
            raise ValueError('servo pin must be GPIO6..GPIO9')
        zero = self.controller.zero_angles[pin-6]
        if isinstance(position, bool) or not isinstance(position, Real) or not -(2**31)-zero <= position <= 2**31-1-zero:
            raise ValueError('servo position must be finite and encodable as a signed 32-bit device angle')
        return self.nudge(pin, position - self.controller.positions[pin-6], now)

    def prepare_camera_switch(self):
        """Camera selection leaves the run latch and reference pose intact."""
        self.controller.status = 'Switching camera - run state retained'

    def resume(self, now):
        self.controller.resume(now, capture_reference=self.control_mode == 'tracking')
        if self.control_mode == 'keyboard':
            self.controller.status = 'Keyboard control - M for tracking'
        if not self.servos_released:
            self._restore_outputs()
        self._next_send = now + 1 / self.config.send_hz
        return True

    def step(self, observation: Observation, now):
        self.tick(now)
        if self.control_mode == 'tracking':
            self.controller.update(observation, now)
        if self.controller.active and not self.servos_released and now >= self._next_send:
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
