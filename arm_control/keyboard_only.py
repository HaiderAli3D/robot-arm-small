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
        self.root.geometry('820x490')
        self.root.minsize(740, 460)
        self.root.configure(bg='#141c27')
        self.closed = False
        self.keys = None
        self.pressed_commands = set()
        self.after_id = None
        self.callback_error = None
        self.root.report_callback_exception = self.callback_failed

        def label(parent, text='', size=12, color='#d9e2ee', **kwargs):
            return tk.Label(parent, text=text, font=('Segoe UI', size),
                            bg='#141c27', fg=color, **kwargs)

        label(self.root, 'Robot Arm', size=24).pack(anchor='w', padx=26, pady=(20, 0))
        label(self.root, 'Keyboard control', color='#9eafc4').pack(anchor='w', padx=28)
        self.banner = label(self.root, size=22, anchor='w', padx=20, pady=9)
        self.banner.pack(fill='x', padx=26, pady=(16, 12))

        cards = tk.Frame(self.root, bg='#141c27')
        cards.pack(fill='x', padx=20)
        self.positions = []
        for column, (pin, name, pair) in enumerate(((6, 'Rotation', '1 / 2'),
                                                   (7, 'Elbow', '4 / 5'),
                                                   (8, 'Wrist', '7 / 8'),
                                                   (9, 'Claw', '3 / 6'))):
            cards.columnconfigure(column, weight=1)
            card = tk.Frame(cards, bg='#202e40', padx=12, pady=12)
            card.grid(row=0, column=column, padx=6, sticky='nsew')
            for text, size, color in ((f'IO{pin}  {name}', 12, '#d9e2ee'),
                                      ('+0°', 25, '#ffffff'),
                                      (f'{pair}   − / +', 12, '#a9bdd4')):
                item = tk.Label(card, text=text, font=('Segoe UI', size), bg='#202e40', fg=color)
                item.pack(pady=3)
                if size == 25:
                    self.positions.append(item)

        self.status = label(self.root, anchor='w')
        self.status.pack(fill='x', padx=28, pady=(15, 3))
        self.connection = label(self.root, size=11, color='#9eafc4', anchor='w', wraplength=750)
        self.connection.pack(fill='x', padx=28)
        buttons = tk.Frame(self.root, bg='#141c27')
        buttons.pack(fill='x', padx=26, pady=14)
        self.toggle_button = None
        for key, text in (('space', 'Resume · Space'), ('c', 'Set zero · C'),
                          ('r', 'Reconnect · R'), ('q', 'Quit · Q')):
            button = tk.Button(buttons, text=text, command=lambda k=key: self.command(k),
                               font=('Segoe UI', 11), bg='#30445e', fg='white',
                               activebackground='#415c7e', activeforeground='white',
                               relief='flat', padx=12, pady=7, takefocus=False)
            button.pack(side='left', padx=(0, 8))
            # Handle shortcuts before Tk's Button class can also activate Space.
            button.bind('<KeyPress>', self.key_down)
            button.bind('<KeyRelease>', self.key_up)
            if key == 'space':
                self.toggle_button = button
        label(self.root, f'Num Lock ON  •  {KEYBOARD_STEP}° per step  •  Hold to repeat  •  Number-row keys also work',
              size=10, color='#9eafc4').pack(anchor='w', padx=28)
        label(self.root, 'Servo keys resume movement. C saves the current commands as zero after 4 seconds.',
              size=10, color='#9eafc4').pack(anchor='w', padx=28, pady=(4, 12))

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
        elif key not in self.pressed_commands:
            self.pressed_commands.add(key)
            self.command(key)
        return 'break'

    def key_up(self, event):
        self.pressed_commands.discard(event.keysym.lower())

    def command(self, key):
        if key not in ('space', 'c', 'r', 'q', 'escape'):
            return
        if self.keys:
            self.keys.cancel()
        now = time.monotonic()
        if key in ('q', 'escape'):
            self.close()
            return
        if key == 'space':
            if self.session.controller.active:
                self.session.pause()
            else:
                self.session.resume(now)
        elif key == 'c':
            self.session.calibrate(now)
        elif key == 'r':
            self.session.connect()
        self.render()

    def render(self):
        controller = self.session.controller
        state = 'RUNNING' if controller.active else 'PAUSED'
        if self.session.link is None:
            state += '  ·  Preview only'
        elif not self.session.connected:
            state += '  ·  USB disconnected'
        self.banner.configure(text=state, bg='#226346' if controller.active else '#765424')
        self.toggle_button.configure(text='Pause · Space' if controller.active else 'Resume · Space')
        self.status.configure(text=controller.status)
        self.connection.configure(text=self.session.connection_status)
        for widget, value in zip(self.positions, controller.positions):
            widget.configure(text=f'{value:+.0f}°')

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
