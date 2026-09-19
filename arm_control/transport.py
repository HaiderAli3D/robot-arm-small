"""Bounded synchronous USB serial transport for robot-arm protocol version 1.

Opening a UART may reset an ESP32 through its adapter's DTR/RTS wiring. Wait
two seconds for that boot to settle, resynchronize any unfinished device input
line, discard stale replies, then explicitly send ``hello`` to freeze outputs
and obtain current angles. The same handshake also works when opening does not
reset the board. Session restores the user's run selection after reconnecting.
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections.abc import Callable, Iterable
from numbers import Real


class LinkError(RuntimeError):
    """Connection, framing, validation, or firmware command failure."""


class SerialLink:
    """One serial owner with at most one transaction in flight.

    ``timeout`` is the total write-and-response budget, at most 0.5 seconds.
    Connect additionally takes a two-second boot-settle interval and one timeout
    budget to resynchronize framing (at most three seconds total by default).
    Optional factory/time callables exercise byte streams without serial hardware.
    """

    def __init__(self, port: str, timeout: float = 0.5, *,
                 serial_factory: Callable | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if not isinstance(timeout, Real) or not 0 < timeout <= 0.5 or not math.isfinite(timeout):
            raise ValueError("timeout must be finite and between 0 and 0.5 seconds")
        self.port = port
        self.timeout = float(timeout)
        self._factory = serial_factory
        self._clock = clock
        self._sleep = sleep
        self._serial = None
        self._resumed = False
        self._lock = threading.Lock()

    def _acquire(self):
        if not self._lock.acquire(blocking=False):
            raise LinkError("A serial transaction is already in progress")

    def _disconnect(self):
        serial, self._serial = self._serial, None
        self._resumed = False
        if serial is not None:
            try:
                serial.close()
            except Exception:
                pass

    def connect(self) -> tuple[float, ...]:
        self._acquire()
        try:
            if self._serial is not None:
                raise LinkError("Already connected; close before reconnecting")
            factory = self._factory
            if factory is None:
                try:
                    import serial
                except ImportError as exc:
                    raise LinkError("pySerial is required; install the project requirements") from exc
                factory = serial.Serial
            self._serial = factory(port=self.port, baudrate=115200,
                                   timeout=self.timeout, write_timeout=self.timeout)
            self._resumed = False
            self._sleep(2.0)
            self._serial.reset_input_buffer()
            self._resynchronize()
            return self._angles_reply(self._exchange("hello"), "ROBOT_ARM 1")
        except Exception as exc:
            self._disconnect()
            if isinstance(exc, LinkError):
                raise
            raise LinkError(f"Could not connect: {exc}") from exc
        finally:
            self._lock.release()

    def _resynchronize(self):
        # Host RX flushing cannot clear a partial command buffered on the board.
        # NUL marks the entire firmware input line invalid before LF terminates
        # it. A bare LF could execute a pending manual move or resume command.
        # Drain the invalid-line reply separately from the fresh hello.
        serial = self._serial
        deadline = self._clock() + self.timeout
        serial.write_timeout = self.timeout
        if serial.write(b"\x00\n") != 2:
            raise LinkError("Incomplete serial framing reset")
        while (remaining := deadline - self._clock()) > 0:
            serial.timeout = remaining
            if not serial.read(min(256, max(1, serial.in_waiting))):
                break
        serial.reset_input_buffer()

    @staticmethod
    def _angles_reply(reply: str, prefix: str) -> tuple[float, ...]:
        match = re.fullmatch(re.escape(prefix) + r" ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)", reply)
        if match is None:
            raise LinkError(f"Malformed firmware response: {reply!r}")
        angles = tuple(float(value) for value in match.groups())
        if any(value > 180 for value in angles):
            raise LinkError("Firmware returned out-of-range angles")
        return angles

    def _exchange(self, command: str) -> str:
        serial = self._serial
        if serial is None:
            raise LinkError("Not connected; reconnect explicitly")
        # Never mistake a queued ACK or unrelated error for the next reply.
        if serial.in_waiting:
            raise LinkError("Unexpected pending firmware data; reconnect explicitly")
        deadline = self._clock() + self.timeout
        payload = (command + "\n").encode("ascii")
        serial.write_timeout = self.timeout
        if serial.write(payload) != len(payload):
            raise LinkError("Incomplete serial write")
        line = bytearray()
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise LinkError("Firmware response timed out")
            serial.timeout = remaining
            chunk = serial.read(1)
            if not chunk:
                raise LinkError("Firmware response timed out or port disconnected")
            if self._clock() > deadline:
                raise LinkError("Firmware response timed out")
            if chunk == b"\n":
                break
            line.extend(chunk)
            if len(line) > 95:
                raise LinkError("Firmware response exceeds 95 bytes")
        try:
            reply = line.removesuffix(b"\r").decode("ascii")
        except UnicodeDecodeError as exc:
            raise LinkError("Firmware response is not ASCII") from exc
        if serial.in_waiting:
            raise LinkError("Unexpected extra firmware response")
        if reply.startswith("ERR "):
            raise LinkError(f"Firmware: {reply[4:]}")
        return reply

    def _command(self, command: str, *, angles=False):
        self._acquire()
        try:
            if command.startswith("pose ") and not self._resumed:
                raise LinkError("Tracking is paused; resume explicitly before sending poses")
            reply = self._exchange(command)
            expected = "OK " + command.split(" ", 1)[0]
            if angles:
                result = self._angles_reply(reply, expected)
                self._resumed = False
                return result
            if reply != expected:
                raise LinkError(f"Expected {expected!r}, received {reply!r}")
            if command == "resume":
                self._resumed = True
        except Exception as exc:
            self._disconnect()
            if isinstance(exc, LinkError):
                raise
            raise LinkError(f"Serial command failed: {exc}") from exc
        finally:
            self._lock.release()

    def resume(self) -> None:
        self._command("resume")

    def hold(self) -> tuple[float, ...]:
        return self._command("hold", angles=True)

    def send_pose(self, angles: Iterable[float]) -> None:
        try:
            values = tuple(angles)
            if len(values) != 4 or any(isinstance(value, bool) or not isinstance(value, Real)
                                      or not 0 <= value <= 180 or not math.isfinite(value)
                                      for value in values):
                raise ValueError("expected four finite angles in 0..180")
        except (TypeError, ValueError) as exc:
            raise LinkError("Pose requires four finite numeric angles in 0..180") from exc
        self._command("pose " + " ".join(str(round(value)) for value in values))

    def close(self) -> None:
        """Best-effort hold with the normal timeout, followed by port release."""
        self._acquire()
        try:
            if self._serial is not None:
                try:
                    self._angles_reply(self._exchange("hold"), "OK hold")
                except Exception:
                    pass
            self._disconnect()
        finally:
            self._lock.release()


def list_ports() -> list[tuple[str, str]]:
    """Enumerate serial devices without opening any of them."""
    try:
        from serial.tools.list_ports import comports
        return [(port.device, port.description) for port in comports()]
    except Exception as exc:
        raise LinkError(f"Could not enumerate serial ports: {exc}") from exc
