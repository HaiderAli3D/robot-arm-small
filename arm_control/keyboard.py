"""Window-scoped servo key presses with a clock-based Windows repeat rate."""

from collections import Counter
import sys
import time

KEYBOARD_STEP = 7
SERVO_KEYS = {
    ord('1'): (6, -KEYBOARD_STEP), ord('2'): (6, KEYBOARD_STEP),
    ord('4'): (7, -KEYBOARD_STEP), ord('5'): (7, KEYBOARD_STEP),
    ord('7'): (8, -KEYBOARD_STEP), ord('8'): (8, KEYBOARD_STEP),
    ord('3'): (9, -KEYBOARD_STEP), ord('6'): (9, KEYBOARD_STEP),
}

VIRTUAL_DIGITS = {vk: ord(str(digit)) for digit in range(1, 9)
                  for vk in (ord(str(digit)), 0x60 + digit)}


class KeyRepeater:
    def __init__(self, repeat_hz):
        self.interval = 1 / repeat_hz
        self.pending = Counter()
        self.due = {}
        self.last_poll = None

    def event(self, vk, flags, now):
        if vk not in VIRTUAL_DIGITS:
            return
        if flags & (1 << 31):
            self.due.pop(vk, None)
        elif not flags & (1 << 30):
            # Only a new physical press counts. Native typematic events are
            # ignored; even a tap wholly between video frames is retained.
            self.pending[VIRTUAL_DIGITS[vk]] += 1
            self.due[vk] = now + self.interval

    def cancel(self):
        self.pending.clear()
        self.due.clear()
        self.last_poll = None

    def poll(self, now, held, focused=True):
        if not focused:
            self.cancel()
            return {}
        counts = self.pending.copy()
        self.pending.clear()
        stalled = self.last_poll is not None and now - self.last_poll > .25
        self.last_poll = now
        for vk, due in list(self.due.items()):
            if vk not in held:
                del self.due[vk]
            elif now >= due:
                if stalled:
                    # A blocked camera/model operation must not replay a
                    # backlog of input. Resume normal cadence from now.
                    self.due[vk] = now + self.interval
                    continue
                count = int((now - due) / self.interval + 1e-7) + 1
                counts[VIRTUAL_DIGITS[vk]] += count
                self.due[vk] += count * self.interval
        return dict(counts)


class WindowsServoKeys:
    """Capture only this UI thread's keys; never install a global input hook.

    The native hook distinguishes first presses from OS repeats and preserves
    short taps. Physical state checks drop repeats immediately on release,
    even if OpenCV has not yet consumed the corresponding key-up message.
    """

    def __init__(self, window):
        import ctypes as c
        from ctypes import wintypes as w

        self.api = u = c.WinDLL('user32', use_last_error=True)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentThreadId.restype = w.DWORD
        thread_id = kernel.GetCurrentThreadId()
        hook_type = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, c.c_size_t, c.c_ssize_t)
        u.SetWindowsHookExW.argtypes = [c.c_int, hook_type, w.HINSTANCE, w.DWORD]
        u.SetWindowsHookExW.restype = w.HANDLE
        u.CallNextHookEx.argtypes = [w.HANDLE, c.c_int, c.c_size_t, c.c_ssize_t]
        u.CallNextHookEx.restype = c.c_ssize_t
        u.UnhookWindowsHookEx.argtypes = [w.HANDLE]
        u.UnhookWindowsHookEx.restype = w.BOOL
        u.FindWindowExW.argtypes = [w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR]
        u.FindWindowExW.restype = w.HWND
        u.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        u.GetWindowThreadProcessId.restype = w.DWORD
        u.GetForegroundWindow.restype = w.HWND
        u.GetAsyncKeyState.argtypes = [c.c_int]
        u.GetAsyncKeyState.restype = c.c_short
        u.SystemParametersInfoW.argtypes = [w.UINT, w.UINT, c.c_void_p, w.UINT]
        u.SystemParametersInfoW.restype = w.BOOL
        self.window = None
        while True:
            self.window = u.FindWindowExW(None, self.window, None, window)
            if not self.window:
                raise RuntimeError('Cannot find the servo control window on this thread')
            if u.GetWindowThreadProcessId(self.window, None) == thread_id:
                break
        speed = w.UINT()
        if not u.SystemParametersInfoW(0x000A, 0, c.byref(speed), 0):
            raise c.WinError(c.get_last_error())
        # Windows exposes 0..31 (approximately 2.5..30 repeats/second).
        self.repeat_hz = 1.5 * (2.5 + 27.5 * speed.value / 31)
        # Start repeating after one interval, without Windows' hold delay.
        self.repeater = KeyRepeater(self.repeat_hz)

        def capture(code, vk, flags):
            if code == 0 and self.focused():
                if vk in VIRTUAL_DIGITS:
                    self.repeater.event(vk, flags, time.monotonic())
                    # Consume digits so HighGUI cannot queue duplicate steps.
                    return 1
                if vk in (32, ord('C'), ord('M')) and flags & (1 << 30) and not flags & (1 << 31):
                    return 1
            return u.CallNextHookEx(None, code, vk, flags)

        self.callback = hook_type(capture)  # Keep callback alive until unhooked.
        self.hook = u.SetWindowsHookExW(2, self.callback, None, thread_id)
        if not self.hook:
            raise c.WinError(c.get_last_error())

    def focused(self):
        return self.api.GetForegroundWindow() == self.window

    def poll(self, now):
        held = {vk for vk in self.repeater.due if self.api.GetAsyncKeyState(vk) & 0x8000}
        return self.repeater.poll(now, held, self.focused())

    def cancel(self):
        self.repeater.cancel()

    def close(self):
        if self.hook:
            self.api.UnhookWindowsHookEx(self.hook)
            self.hook = None


def create_servo_keys(window):
    return WindowsServoKeys(window) if sys.platform == 'win32' else None
