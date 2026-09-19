"""Poll-driven camera selection that preserves the active camera while probing."""

from __future__ import annotations

import time
from collections.abc import Callable

from .camera import Camera


class CameraSwitcher:
    """Probe cameras without waiting for reads or changing tracking/session state.

    Call ``poll`` from the GUI loop. Only a fresh candidate frame replaces the
    active camera. Camera construction/start are asynchronous, reads use a zero
    timeout, and cleanup uses Camera's bounded close operation.
    """

    def __init__(self, current_camera: Camera, index: int, width: int, height: int, *,
                 camera_factory: Callable = Camera, clock: Callable = time.monotonic,
                 probe_timeout: float = 3.0):
        if not 0 < probe_timeout < float("inf"):
            raise ValueError("probe_timeout must be finite and positive")
        self.camera = current_camera
        self.index = index
        self.switching = False
        self.status = f"Camera {index}"
        self._width = width
        self._height = height
        self._factory = camera_factory
        self._clock = clock
        self._probe_timeout = probe_timeout
        self._indices = list(dict.fromkeys([0, 1, 2, 3, index]))
        self._remaining: list[int] = []
        self._pending: Camera | None = None
        self._pending_index = index
        self._deadline = 0.0
        self._closed = False

    def request_next(self) -> bool:
        if self._closed or self.switching:
            return False
        current = self._indices.index(self.index)
        self._remaining = self._indices[current + 1:] + self._indices[:current]
        self.switching = True
        self._advance()
        return True

    @staticmethod
    def _close_camera(camera: Camera | None):
        if camera is not None:
            try:
                camera.close()
            except Exception:
                pass

    def _advance(self):
        if not self._remaining:
            self.switching = False
            self.status = f"No other camera available; keeping camera {self.index}"
            return
        self._pending_index = self._remaining.pop(0)
        self.status = f"Looking for another camera: trying camera {self._pending_index}"
        self._deadline = self._clock() + self._probe_timeout
        try:
            self._pending = self._factory(self._pending_index, self._width, self._height)
            self._pending.start()
        except Exception:
            pending, self._pending = self._pending, None
            self._close_camera(pending)
            # Continue on the next GUI poll rather than looping through every
            # failing driver in one UI event.
            if not self._remaining:
                self.switching = False
                self.status = f"No other camera available; keeping camera {self.index}"

    def poll(self) -> bool:
        if self._closed or not self.switching:
            return False
        if self._pending is None:
            self._advance()
            return False
        candidate = self._pending
        try:
            failed = candidate.error is not None or self._clock() >= self._deadline
            frame = None if failed else candidate.latest(timeout=0)
            failed = failed or candidate.error is not None
        except Exception:
            failed, frame = True, None
        if failed:
            self._pending = None
            self._close_camera(candidate)
            self._advance()
            return False
        if frame is None or frame.image is None or not 0 <= self._clock() - frame.captured_at < 0.5:
            return False
        previous = self.camera
        self.camera = candidate
        self.index = self._pending_index
        self._pending = None
        self._remaining = []
        self.switching = False
        self.status = f"Camera {self.index} selected"
        self._close_camera(previous)
        return True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.switching = False
        pending, self._pending = self._pending, None
        self._remaining = []
        self._close_camera(pending)
        if self.camera is not pending:
            self._close_camera(self.camera)
        self.status = "Camera closed"
