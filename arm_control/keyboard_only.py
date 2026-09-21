"""Standalone keyboard controller: standard-library UI and USB serial only."""

import argparse
import math
import sys
import time

from .config import Config
from .keyboard import KEYBOARD_STEP, SERVO_KEYS, create_servo_keys
from .session import Session
from .transport import SerialLink, list_ports

WINDOW = 'Robot arm - Keyboard'


class KeyboardSession(Session):
    """Use the shared USB/run-state logic without accepting observations."""

    def __init__(self, link=None):
        super().__init__(Config(), link)
        self.control_mode = 'keyboard'
        self.zero_at = None
        self.controller.status = 'Ready - choose a servo key or press Space'

    def resume(self, now):
        result = super().resume(now)
        self.controller.status = 'Keyboard control active'
        return result

    def nudge(self, pin, delta, now):
        super().nudge(pin, delta, now)
        self.zero_at = None
        self.controller.status = f'IO{pin}: {self.controller.positions[pin - 6]:+.0f} degrees'

    def calibrate(self, now):
        if not math.isfinite(now):
            raise ValueError('time must be finite')
        self.zero_at = now + 4.0
        self.controller.status = 'Zeroing in 4 seconds - current position held'

    def tick(self, now):
        if self.zero_at is not None:
            if now >= self.zero_at:
                self.controller.zero_current_positions()
                self.zero_at = None
                self.controller.status = 'Current positions zeroed'
            else:
                self.controller.status = f'Zeroing in {math.ceil(self.zero_at - now)} seconds - current position held'
        # Keyboard mode skips Controller.update entirely: no pose is required.
        return super().step(None, now)


class KeyboardWindow:
    def __init__(self, session):
        import tkinter as tk

        self.session = session
        self.root = tk.Tk()
        self.root.title(WINDOW)
        width = min(1200, self.root.winfo_screenwidth() - 80)
        height = min(860, self.root.winfo_screenheight() - 100)
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(980, width), min(680, height))
        self.closed = False
        self.keys = None
        self.pressed_commands = set()
        self.after_id = None
        self.callback_error = None
        self.root.report_callback_exception = self.callback_failed

        from .console_view import ConsoleView
        self.view = ConsoleView(self.root, self.command, self.nudge)
        for button in self.view.buttons:
            # Global shortcuts win over Tk Button's own Space binding.
            button.bind('<KeyPress>', self.key_down)
            button.bind('<KeyRelease>', self.key_up)
            button.bind('<Return>', lambda event, target=button: self.activate_button(target))

        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<KeyPress>', self.key_down)
        self.root.bind('<KeyRelease>', self.key_up)
        self.root.bind('<FocusOut>', self.focus_lost)
        self.root.update()
        try:
            self.keys = create_servo_keys(WINDOW)
        except Exception:
            self.root.destroy()
            raise
        self.render()

    def focus_lost(self, event=None):
        if self.keys:
            self.keys.cancel()
        self.pressed_commands.clear()

    def callback_failed(self, error_type, error, traceback):
        self.callback_error = error.with_traceback(traceback)
        self.close()

    def key_down(self, event):
        key = event.keysym.lower()
        if self.keys is None and event.char and ord(event.char) in SERVO_KEYS:
            pin, delta = SERVO_KEYS[ord(event.char)]
            self.session.nudge(pin, delta, time.monotonic())
        elif key in ('space', 'c', 'r', 'q', 'escape', 'f11'):
            if key not in self.pressed_commands:
                self.pressed_commands.add(key)
                self.command(key)
        else:
            return None
        return 'break'

    def key_up(self, event):
        key = event.keysym.lower()
        self.pressed_commands.discard(key)
        if key in ('space', 'c', 'r', 'q', 'escape', 'f11', 'return'):
            return 'break'

    def activate_button(self, button):
        if 'return' not in self.pressed_commands:
            self.pressed_commands.add('return')
            button.invoke()
        return 'break'

    def command(self, key):
        if key not in ('space', 'c', 'r', 'q', 'escape', 'f11'):
            return
        if self.keys:
            self.keys.cancel()
        now = time.monotonic()
        if key in ('q', 'escape'):
            self.close()
            return
        if key == 'f11':
            # Tk recreates the Windows wrapper HWND when toggling fullscreen.
            # Rebind native key ownership to that new window before continuing.
            if self.keys:
                self.keys.close()
                self.keys = None
            fullscreen = not self.root.attributes('-fullscreen')
            self.root.attributes('-fullscreen', fullscreen)
            self.root.update_idletasks()
            self.keys = create_servo_keys(self.root.title())
            self.view.fullscreen_button.configure(text='Windowed   F11' if fullscreen else 'Fullscreen   F11')
        elif key == 'space':
            if self.session.controller.active:
                self.session.pause()
            else:
                self.session.resume(now)
        elif key == 'c':
            self.session.calibrate(now)
        elif key == 'r':
            self.session.connect()
        self.render()

    def nudge(self, pin, delta):
        if self.keys:
            self.keys.cancel()
        self.session.nudge(pin, delta, time.monotonic())
        self.render()

    def render(self):
        self.view.update(self.session, time.monotonic())

    def tick(self):
        if self.closed:
            return
        try:
            now = time.monotonic()
            if self.keys:
                deltas = {}
                for digit, count in self.keys.poll(now).items():
                    pin, delta = SERVO_KEYS[digit]
                    deltas[pin] = deltas.get(pin, 0) + delta * count
                for pin, delta in deltas.items():
                    if delta:
                        self.session.nudge(pin, delta, now)
            self.session.tick(now)
            self.render()
        except Exception:
            # Ensure an unexpected UI error releases serial ownership.
            self.close()
            raise
        self.after_id = self.root.after(10, self.tick)

    def run(self):
        try:
            self.session.connect()
            print(self.session.connection_status, flush=True)
            self.tick()
            self.root.mainloop()
            if self.callback_error is not None:
                raise self.callback_error
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        try:
            if self.keys:
                self.keys.close()
        finally:
            try:
                self.session.close()
            finally:
                self.root.destroy()


def build_parser():
    parser = argparse.ArgumentParser(description='Robot arm keyboard controller')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--port', help='USB UART port, e.g. COM70; enables live control')
    mode.add_argument('--dry-run', action='store_true', help='Preview without a serial connection (default)')
    parser.add_argument('--list-ports', action='store_true', help='List serial ports and exit')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.list_ports:
            for port, description in list_ports():
                print(f'{port}: {description}')
            return 0
        session = KeyboardSession(SerialLink(args.port) if args.port else None)
        KeyboardWindow(session).run()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
