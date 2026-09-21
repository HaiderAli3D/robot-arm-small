"""Presentation for the keyboard console. No device or input ownership."""

from collections import deque
import math
import tkinter as tk

from .arm_stage import ArmStage

BG = '#10182a'
PANEL = '#152138'
LINE = '#293750'
TEXT = '#edf2fa'
MUTED = '#9aabc4'
ACCENTS = ('#9faeff', '#67ced0', '#d6b989', '#b8a5de')
FONT = 'Segoe UI'
DISPLAY = 'Bahnschrift'


def text(parent, value, size=11, color=TEXT, background=BG, **kwargs):
    return tk.Label(parent, text=value, font=(FONT, size), fg=color, bg=background, **kwargs)


class JointDial(tk.Canvas):
    def __init__(self, parent, color):
        super().__init__(parent, width=58, height=58, bg=PANEL, highlightthickness=0)
        self.color = color
        self.last = None

    def show(self, angle, highlighted):
        signature = (angle, highlighted)
        if signature == self.last:
            return
        self.last = signature
        self.delete('all')
        self.create_oval(7, 7, 51, 51, outline=LINE, width=2)
        for i in range(12):
            a = math.tau * i / 12
            self.create_line(29 + 24 * math.sin(a), 29 - 24 * math.cos(a),
                             29 + 27 * math.sin(a), 29 - 27 * math.cos(a), fill=LINE)
        a = math.radians(angle % 360)
        self.create_line(29, 29, 29 + 18 * math.sin(a), 29 - 18 * math.cos(a),
                         fill=self.color, width=3, capstyle='round')
        self.create_oval(25, 25, 33, 33, fill=self.color, outline='')
        if highlighted:
            self.create_oval(3, 3, 55, 55, outline=self.color, width=1)


class CommandHistory(tk.Canvas):
    """Eight seconds of actual commands on a common, automatically scaled axis."""

    def __init__(self, parent):
        super().__init__(parent, height=92, bg=PANEL, highlightthickness=0)
        self.samples = deque(maxlen=260)
        self.last_draw = -math.inf
        self.last_size = None

    def sample(self, now, angles):
        if self.samples and now - self.samples[-1][0] < 0.033:
            return
        self.samples.append((now, tuple(v - 90 for v in angles)))
        while self.samples and self.samples[0][0] < now - 8:
            self.samples.popleft()
        size = (self.winfo_width(), self.winfo_height())
        if now - self.last_draw < .1 and size == self.last_size:
            return
        self.last_draw, self.last_size = now, size
        w, h = size
        if w < 40:
            return
        self.delete('all')
        left, right, top, bottom = 46, w - 12, 8, h - 22
        values = [v for _, row in self.samples for v in row]
        low, high = min(min(values), -10), max(max(values), 10)
        pad = (high - low) * .12
        low, high = low - pad, high + pad
        for fraction in (0, .5, 1):
            y = top + (bottom - top) * fraction
            self.create_line(left, y, right, y, fill=LINE)
            value = high - (high - low) * fraction
            label = f'{value:.0f}' if abs(value) < 10000 else f'{value:.0e}'
            self.create_text(left - 8, y, text=label, anchor='e', fill=MUTED, font=(FONT, 8))
        for seconds in (8, 6, 4, 2, 0):
            x = right - seconds / 8 * (right - left)
            self.create_text(x, h - 7, text=f'−{seconds}s' if seconds else 'Now',
                             fill=MUTED, font=(FONT, 8))
        for channel, color in enumerate(ACCENTS):
            points = []
            for stamp, row in self.samples:
                points.extend((right - (now - stamp) / 8 * (right - left),
                               bottom - (row[channel] - low) / (high - low) * (bottom - top)))
            if len(points) >= 4:
                self.create_line(*points, fill=color, width=2)


class ConsoleView:
    def __init__(self, root, command, nudge):
        self.root = root
        self.command = command
        self.buttons = []
        self.last_state = None
        self.last_angles = None
        self.changed_at = [0.] * 4
        self.compact = False
        root.configure(bg=BG)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = tk.Frame(root, bg=BG)
        header.grid(row=0, column=0, sticky='ew', padx=28, pady=(22, 18))
        logo = tk.Canvas(header, width=44, height=44, bg=BG, highlightthickness=0)
        logo.pack(side='left', padx=(0, 14))
        logo.create_line(8, 33, 16, 12, 33, 19, 30, 30, fill=ACCENTS[0], width=4, capstyle='round')
        for x, y in ((8, 33), (16, 12), (33, 19)):
            logo.create_oval(x-4, y-4, x+4, y+4, fill=BG, outline=TEXT, width=2)
        title = tk.Frame(header, bg=BG)
        title.pack(side='left')
        tk.Label(title, text='Robot arm', font=(DISPLAY, 24), fg=TEXT, bg=BG).pack(anchor='w')
        text(title, 'Four-axis control', size=10, color=MUTED).pack(anchor='w')
        self.state_badge = text(header, 'Paused', size=13, padx=17, pady=8)
        self.state_badge.pack(side='right')
        self.link_badge = text(header, 'Preview', size=10, color=MUTED)
        self.link_badge.pack(side='right', padx=20)

        viewport_frame = tk.Frame(root, bg=BG)
        viewport_frame.grid(row=1, column=0, sticky='nsew', padx=28)
        viewport_frame.rowconfigure(0, weight=1)
        viewport_frame.columnconfigure(0, weight=1)
        viewport = tk.Canvas(viewport_frame, bg=BG, highlightthickness=0)
        viewport.grid(row=0, column=0, sticky='nsew')
        scrollbar = tk.Scrollbar(viewport_frame, orient='vertical', command=viewport.yview)
        viewport.configure(yscrollcommand=scrollbar.set)
        body = tk.Frame(viewport, bg=BG)
        body_item = viewport.create_window(0, 0, window=body, anchor='nw')
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=320)
        left = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 18))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        stage_head = tk.Frame(left, bg=PANEL)
        stage_head.grid(row=0, column=0, sticky='ew', padx=22, pady=(18, 0))
        text(stage_head, 'Commanded pose', size=13, background=PANEL).pack(side='left')
        text(stage_head, 'Schematic', size=10, color=MUTED, background=PANEL).pack(side='right')
        self.stage = ArmStage(left, bg=PANEL, highlightthickness=0, height=360)
        self.stage.grid(row=1, column=0, sticky='nsew', padx=4)
        text(left, 'Illustrative geometry. Positions are commands, not sensor feedback.', size=9,
             color=MUTED, background=PANEL).grid(row=2, column=0, sticky='w', padx=22, pady=(0, 16))
        tk.Frame(left, height=1, bg=LINE).grid(row=3, column=0, sticky='ew', padx=22)
        history_head = tk.Frame(left, bg=PANEL)
        history_head.grid(row=4, column=0, sticky='ew', padx=22, pady=(13, 4))
        text(history_head, 'Command history', size=10, background=PANEL).pack(side='left')
        text(history_head, 'Degrees from boot center', size=9, color=MUTED, background=PANEL).pack(side='right')
        self.history = CommandHistory(left)
        self.history.grid(row=5, column=0, sticky='ew', padx=10, pady=(0, 9))

        right = tk.Frame(body, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        right.grid(row=0, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        joint_heading = text(right, 'Joint control', size=16, background=PANEL)
        joint_heading.grid(row=0, column=0, sticky='w', padx=20, pady=(18, 3))
        joint_hint = text(right, '7° steps  /  Hold a key to repeat', size=10, color=MUTED, background=PANEL)
        joint_hint.grid(row=1, column=0, sticky='w', padx=20, pady=(0, 12))
        self.joints = []
        joint_names = []
        for i, (name, pair) in enumerate((('Rotation', ('1','2')), ('Elbow', ('4','5')),
                                         ('Wrist', ('7','8')), ('Claw', ('3','6')))):
            row = tk.Frame(right, bg=PANEL)
            row.grid(row=2+i, column=0, sticky='nsew', padx=20)
            right.rowconfigure(2+i, weight=1)
            row.columnconfigure(1, weight=1)
            tk.Frame(row, height=1, bg=LINE).grid(row=0, column=0, columnspan=3, sticky='ew')
            dial = JointDial(row, ACCENTS[i])
            dial.grid(row=1, column=0, rowspan=2, padx=(0,10), pady=7)
            name_label = text(row, name, size=11, background=PANEL)
            name_label.grid(row=1, column=1, sticky='sw', pady=(10,0))
            joint_names.append(name_label)
            text(row, f'IO{i+6}', size=9, color=ACCENTS[i], background=PANEL).grid(row=1, column=2, sticky='se')
            position = tk.Label(row, text='+0°', font=(DISPLAY, 25), bg=PANEL, fg=TEXT, anchor='w')
            position.grid(row=2, column=1, sticky='nw', pady=(0,10))
            keys = tk.Frame(row, bg=PANEL)
            keys.grid(row=2, column=2, sticky='e', pady=(0,10))
            for digit, direction in zip(pair, (-1, 1)):
                button = self.button(keys, f'{digit}   {"−" if direction < 0 else "+"}',
                                     lambda pin=i+6, d=direction: nudge(pin, d*7), compact=True)
                button.pack(side='left', padx=(0,7))
            self.joints.append((dial, position))
        joint_footer = text(right, 'Numpad or number row. Num Lock on.', size=9, color=MUTED, background=PANEL)
        joint_footer.grid(row=6, column=0, sticky='w', padx=20, pady=(8,17))

        footer = tk.Frame(root, bg=BG)
        footer.grid(row=2, column=0, sticky='ew', padx=28, pady=(15, 18))
        footer.columnconfigure(0, weight=1)
        self.status = text(footer, '', size=11, anchor='w')
        self.status.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.connection = text(footer, '', size=9, color=MUTED, anchor='w', wraplength=950)
        self.connection.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(3,12))
        actions = tk.Frame(footer, bg=BG)
        actions.grid(row=2, column=0, sticky='w')
        self.toggle = self.button(actions, 'Resume    Space', lambda: command('space'), primary=True)
        self.toggle.pack(side='left', padx=(0,10))
        self.zero = self.button(actions, 'Set zero    C', lambda: command('c'))
        self.zero.pack(side='left', padx=(0,10))
        self.button(actions, 'Reconnect    R', lambda: command('r')).pack(side='left')
        extra = tk.Frame(footer, bg=BG)
        extra.grid(row=2, column=1, sticky='e')
        self.fullscreen_button = self.button(extra, 'Fullscreen   F11', lambda: command('f11'))
        self.fullscreen_button.pack(side='left', padx=(0,10))
        self.button(extra, 'Quit   Q', lambda: command('q')).pack(side='left')

        def fit_body(event=None):
            width, height = viewport.winfo_width(), viewport.winfo_height()
            if width < 10:
                return
            if viewport_frame.winfo_width() < 850:
                left.grid_remove()
                right.grid_configure(column=0)
                body.columnconfigure(1, minsize=0)
            else:
                left.grid()
                right.grid_configure(column=1)
                body.columnconfigure(1, minsize=320)
            compact = height < 560
            if compact != self.compact:
                self.compact = compact
                for name, (_, position) in zip(joint_names, self.joints):
                    name.configure(font=(FONT, 10 if compact else 11))
                    name.grid_configure(pady=(4 if compact else 10, 0))
                    position.configure(font=(DISPLAY, 20 if compact else 25))
                    position.grid_configure(pady=(0, 4 if compact else 10))
                joint_heading.grid_configure(pady=(10, 0) if compact else (18, 3))
                joint_hint.grid_configure(pady=(0, 6 if compact else 12))
                joint_footer.grid_configure(pady=(5, 10) if compact else (8, 17))
            self.stage.configure(height=220 if compact else 360)
            if compact:
                history_head.grid_remove()
                self.history.grid_remove()
            else:
                history_head.grid()
                self.history.grid()
            needed = body.winfo_reqheight()
            viewport.itemconfigure(body_item, width=width, height=max(height, needed))
            viewport.configure(scrollregion=(0, 0, width, max(height, needed)))
            if needed > height + 2:
                scrollbar.grid(row=0, column=1, sticky='ns')
            else:
                scrollbar.grid_remove()
                viewport.yview_moveto(0)

        viewport.bind('<Configure>', fit_body)
        body.bind('<Configure>', fit_body)

    def button(self, parent, label, callback, *, primary=False, compact=False):
        background = ACCENTS[0] if primary else '#253650'
        foreground = BG if primary else TEXT
        button = tk.Button(parent, text=label, command=callback, font=(FONT, 10),
                           fg=foreground, bg=background, activebackground='#b2beff' if primary else '#354b6d',
                           activeforeground=foreground, relief='flat', borderwidth=0,
                           highlightthickness=1, highlightbackground=background, highlightcolor=TEXT,
                           padx=12 if compact else 16, pady=4 if compact else 10, cursor='hand2', takefocus=True)
        button.bind('<Enter>', lambda e: button.configure(bg='#b2beff' if primary else '#354b6d'))
        button.bind('<Leave>', lambda e: button.configure(bg=background))
        self.buttons.append(button)
        return button

    def update(self, session, now):
        controller = session.controller
        angles, positions = controller.angles, controller.positions
        if self.last_angles is not None:
            for i, (before, after) in enumerate(zip(self.last_angles, angles)):
                if before != after:
                    self.changed_at[i] = now
        self.last_angles = angles
        for i, (dial, position) in enumerate(self.joints):
            dial.show(positions[i], now - self.changed_at[i] < .3)
            value = f'{positions[i]:+.0f}°'
            if position.cget('text') != value:
                position.configure(text=value, font=(DISPLAY, (20 if self.compact else 25) if len(value)<9 else 16))
        self.stage.update_pose(angles, positions, controller.active, now)
        self.history.sample(now, angles)
        remaining = max(0, math.ceil(session.zero_at - now)) if session.zero_at is not None else None
        state = (controller.active, session.connected, controller.status, session.connection_status, remaining)
        if state == self.last_state:
            return
        self.last_state = state
        self.state_badge.configure(text='●  Running' if controller.active else '●  Paused',
                                   fg=ACCENTS[1] if controller.active else ACCENTS[2],
                                   bg='#183736' if controller.active else '#352f28')
        if session.link is None:
            link = 'Preview only'
        elif session.connected:
            link = f'USB / {getattr(session.link, "port", "Connected")}'
        else:
            link = 'USB disconnected'
        self.link_badge.configure(text=link)
        self.toggle.configure(text='Pause    Space' if controller.active else 'Resume    Space')
        self.zero.configure(text=f'Zero in {remaining}s' if remaining is not None else 'Set zero    C')
        self.status.configure(text=controller.status)
        self.connection.configure(text=session.connection_status)
