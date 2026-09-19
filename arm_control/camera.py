"""Background camera capture with one latest-frame slot and bounded UI waits."""

from __future__ import annotations

from dataclasses import dataclass
import math
import sys
import threading
import time
from typing import Any, Callable


@dataclass(frozen=True)
class CapturedFrame:
    sequence: int
    captured_at: float
    image: Any


def _open_capture(index: int, width: int, height: int):
    import cv2

    backends = (cv2.CAP_MSMF, cv2.CAP_DSHOW) if sys.platform == "win32" else (cv2.CAP_ANY,)
    for backend in backends:
        capture = cv2.VideoCapture(index, backend)
        if not capture.isOpened():
            capture.release()
            continue
        # Keep the driver's native format. Some virtual cameras accept property
        # setters but then return black frames; processing size is set in software.
        return capture
    raise OSError(f"Could not open camera {index}")


class Camera:
    """Daemon capture worker; the GUI never calls a blocking driver read.

    The optional factory receives ``(index, width, height)`` and returns an
    opened capture object with ``read()`` and ``release()``. Only the worker
    accesses that object, including release. A stuck driver may leave a daemon
    alive until process exit; ``close()`` still returns within a bounded wait.
    Width and height bound the processed image, preserving aspect ratio without
    upscaling. They do not request a different hardware capture format.
    """

    def __init__(self, index: int, width: int, height: int, *,
                 capture_factory: Callable | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._index = index
        self._width = width
        self._height = height
        self._factory = capture_factory or _open_capture
        self._clock = clock
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._frame: CapturedFrame | None = None
        self._error: str | None = None

    @property
    def error(self) -> str | None:
        with self._condition:
            return self._error

    def start(self) -> Camera:
        with self._condition:
            if self._stop.is_set():
                raise RuntimeError("Camera is closed; create a new Camera to reopen it")
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="camera-capture", daemon=True)
                self._thread.start()
        return self

    def _run(self):
        capture = None
        try:
            capture = self._factory(self._index, self._width, self._height)
            sequence = 0
            while not self._stop.is_set():
                success, image = capture.read()
                captured_at = self._clock()
                if self._stop.is_set():
                    break
                if not success or image is None:
                    raise OSError("Camera capture failed or device disconnected")
                image_height, image_width = image.shape[:2]
                scale = min(self._width / image_width, self._height / image_height, 1.0)
                if scale < 1.0:
                    import cv2

                    size = (max(1, round(image_width * scale)), max(1, round(image_height * scale)))
                    image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
                sequence += 1
                with self._condition:
                    if self._stop.is_set():
                        break
                    self._frame = CapturedFrame(sequence, captured_at, image)
                    self._condition.notify_all()
        except Exception as exc:
            with self._condition:
                if not self._stop.is_set():
                    self._error = str(exc) or type(exc).__name__
                self._stop.set()
                self._condition.notify_all()
        finally:
            if capture is not None:
                try:
                    capture.release()
                except Exception as exc:
                    with self._condition:
                        if not self._stop.is_set():
                            self._error = f"Camera release failed: {exc}"
            with self._condition:
                self._stop.set()
                self._condition.notify_all()

    def latest(self, after: int = -1, timeout: float = 0.05) -> CapturedFrame | None:
        if timeout < 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be finite and nonnegative")
        # Wait deadlines use actual monotonic time, independently of the optional
        # capture timestamp clock, so a test clock cannot create an infinite wait.
        with self._condition:
            self._condition.wait_for(
                lambda: self._stop.is_set() or (self._frame is not None and self._frame.sequence > after),
                timeout=timeout,
            )
            if self._stop.is_set():
                return None
            if self._frame is not None and self._frame.sequence > after:
                return self._frame
            return None

    def close(self) -> None:
        with self._condition:
            self._stop.set()
            self._frame = None
            self._condition.notify_all()
            worker = self._thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0.25)
