"""A responsive, dependency-free schematic of the arm's commanded pose.

This is an illustration, not forward kinematics or position feedback.  Bounded
display transforms deliberately keep even extreme commands inside the viewport.
They never alter the commands sent to the arm.
"""

import math
import tkinter as tk


class ArmStage(tk.Canvas):
    """Draw the four commanded joints on a quiet, dimensional technical stage."""

    BACKGROUND = '#10182a'
    ACCENTS = ('#9faeff', '#67ced0', '#d6b989', '#b8a5de')

    def __init__(self, parent, **kwargs):
        if 'background' not in kwargs and 'bg' not in kwargs:
            kwargs['background'] = self.BACKGROUND
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('borderwidth', 0)
        super().__init__(parent, **kwargs)
        self._angles = (90.0,) * 4
        self._positions = (0.0,) * 4
        self._active = False
        self._signature = None
        self.bind('<Configure>', self._resize, add='+')

    def update_pose(self, angles, positions, active, now=None):
        """Refresh only when the pose, display values, or run state changes."""
        def finite(values, fallback):
            result = []
            for value in values:
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError):
                    number = fallback
                result.append(number if math.isfinite(number) else fallback)
            return tuple((result + [fallback] * 4)[:4])

        self._angles = finite(angles, 90.0)
        self._positions = finite(positions, 0.0)
        self._active = bool(active)
        self._draw()

    def _resize(self, event):
        self._draw()

    def _draw(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 10 or height < 10:
            return
        signature = (width, height, self._angles, self._positions, self._active)
        if signature == self._signature:
            return
        self._signature = signature
        self.delete('all')
        scale = min(width / 760.0, height / 500.0)
        ox, oy = (width - 760 * scale) / 2, (height - 500 * scale) / 2

        def coords(points):
            return [coordinate for x, y in points
                    for coordinate in (ox + x * scale, oy + y * scale)]

        def line(points, color, weight=1, **kwargs):
            return self.create_line(*coords(points), fill=color,
                                    width=max(1, weight * scale), **kwargs)

        def polygon(points, color, outline='', weight=1):
            return self.create_polygon(*coords(points), fill=color,
                                       outline=outline, width=max(1, weight * scale))

        def ellipse(x, y, rx, ry, color, outline='', weight=1):
            return self.create_oval(*coords(((x-rx, y-ry), (x+rx, y+ry))),
                                    fill=color, outline=outline,
                                    width=max(1, weight * scale))

        def text(x, y, value, color='#94a4bd', size=10, anchor='w', bold=False):
            return self.create_text(*coords(((x, y),)), text=value, fill=color,
                                    anchor=anchor, font=('Segoe UI', max(8, round(size*scale)),
                                                        'bold' if bold else 'normal'))

        # Perspective floor: a bounded set of lines, not simulated sensor data.
        for end_x in range(-80, 841, 80):
            line(((360 + (end_x-360)*.29, 331), (end_x, 477)), '#1a2941')
        for row in (341, 355, 374, 400, 434, 477):
            spread = 160 + (row-331)*1.9
            line(((max(24, 360-spread), row), (min(736, 360+spread), row)), '#1a2941')
        # Broken horizon and construction axes soften the otherwise empty space.
        line(((34, 331), (177, 331)), '#26344e')
        line(((544, 331), (726, 331)), '#26344e')
        line(((300, 92), (300, 424)), '#1e2d45', dash=(2, 6))
        line(((113, 407), (532, 407)), '#26344e', dash=(3, 6))

        # Use saturating display transforms, so signed 32-bit commands remain
        # finite and legible.  The readout remains the actual nominal command.
        yaw, elbow, wrist, claw = self._angles
        turn = math.tanh((yaw-90.0)/150.0)
        bend = math.tanh((elbow-90.0)/100.0)
        flex = math.tanh((wrist-90.0)/110.0)
        opening = 1.0 - min(1.0, abs(claw-90.0)/95.0)
        shoulder = (304.0, 352.0)
        joint = (272.0 + turn*35.0, 204.0)
        arm_angle = math.radians(-8.0 + bend*45.0)
        end = (joint[0] + 147*math.cos(arm_angle),
               joint[1] + 147*math.sin(arm_angle))
        hand_angle = math.radians(max(-10.0, min(110.0,
                                    math.degrees(arm_angle) + 32.0 + flex*69.0)))
        hand_end = (end[0] + 59*math.cos(hand_angle),
                    end[1] + 59*math.sin(hand_angle))

        # Layered footprint and plinth, with a yaw indicator on the upper ring.
        ellipse(313, 430, 136, 26, '#0b1120')
        ellipse(312, 421, 112, 28, '#182438', '#2c3c56')
        polygon(((208, 399), (416, 399), (416, 418), (396, 431),
                 (229, 431), (208, 418)), '#202e44', '#3b4b65')
        ellipse(312, 399, 104, 27, '#36465e', '#586a85')
        ellipse(312, 397, 88, 20, '#1b2a42', '#75849b')
        ellipse(312, 397, 68, 15, '#2c3f59', '#536985')
        for angle in (25, 85, 145, 205, 265, 325):
            rad = math.radians(angle)
            ellipse(312+94*math.cos(rad), 399+22*math.sin(rad), 2.6, 1.4, '#a4aec0')
        rotation = math.radians(-65 + turn*130)
        indicator = (312+80*math.cos(rotation), 397+17*math.sin(rotation))
        ellipse(*indicator, 5, 2.5, self.ACCENTS[0])
        polygon(((274, 394), (274, 354), (284, 336), (322, 336),
                 (345, 354), (345, 394), (317, 404)), '#293b54', '#576d8a')
        polygon(((322, 336), (345, 354), (345, 394), (323, 386)), '#1a2a41')
        line(((279, 382), (279, 357), (287, 343), (307, 343)), '#72849c', 2)

        def link(start, finish, radius, accent):
            dx, dy = finish[0]-start[0], finish[1]-start[1]
            length = math.hypot(dx, dy)
            ux, uy = dx/length, dy/length
            nx, ny = -uy, ux

            def point(along, across):
                return (start[0]+ux*along+nx*across,
                        start[1]+uy*along+ny*across)

            body = [point(8, -radius), point(length-12, -radius*.76),
                    point(length-4, 0), point(length-12, radius*.76),
                    point(8, radius), point(-2, 0)]
            shadow = [(x+10, y+11) for x, y in body]
            polygon(shadow, '#0a1220')
            polygon([(x+7, y+7) for x, y in body], '#1f2f47', '#344b68')
            polygon(body, '#52647d', '#8090a7')
            polygon((point(16, -radius+4), point(length-21, -radius*.76+4),
                     point(length-28, 0), point(19, radius-6)), '#40536e')
            line((point(19, -radius+4), point(length-24, -radius*.76+4)), '#a6b2c4', 1.5)
            line((point(24, radius-5), point(length-24, radius*.76-5)), accent, 2)
            line((point(30, -3), point(length-29, -3)), '#25364f', 5)
            line((point(30, -4), point(length-29, -4)), '#6d7e97', 1)
            for along in (22, length-23):
                bolt = point(along, radius-9)
                ellipse(*bolt, 2.5, 2.5, '#bdc7d4', '#31435e')

        def bearing(center, radius, accent, direction):
            x, y = center
            ellipse(x+5, y+6, radius+3, radius+3, '#101c2f', '#3b4e69')
            ellipse(x, y, radius, radius, '#293b55', '#8796aa', 1.4)
            ellipse(x, y, radius-5, radius-5, '#18283f', '#526883')
            ellipse(x, y, radius-10, radius-10, '#415571', accent, 2)
            ellipse(x, y, 5, 5, '#202f45', '#95a2b6')
            dx, dy = math.cos(direction), math.sin(direction)
            line(((x+dx*(radius-7), y+dy*(radius-7)),
                  (x+dx*(radius-1), y+dy*(radius-1))), accent, 3)
            for bolt_angle in (45, 135, 225, 315):
                rad = math.radians(bolt_angle)
                ellipse(x+(radius-3)*math.cos(rad), y+(radius-3)*math.sin(rad),
                        1.4, 1.4, '#a1aec0')

        # Dark cable behind the two machined links.
        line(((shoulder[0]+20, shoulder[1]), (joint[0]+30, joint[1]+30),
              (end[0]+9, end[1]+16)), '#080f1c', 9, smooth=True)
        line(((shoulder[0]+20, shoulder[1]), (joint[0]+30, joint[1]+30),
              (end[0]+9, end[1]+16)), '#31445d', 3, smooth=True)
        link(shoulder, joint, 29, self.ACCENTS[0])
        link(joint, end, 23, self.ACCENTS[1])
        link(end, hand_end, 16, self.ACCENTS[2])
        bearing(shoulder, 33, self.ACCENTS[0], -math.pi/2+turn)
        bearing(joint, 29, self.ACCENTS[1], arm_angle)
        bearing(end, 24, self.ACCENTS[2], hand_angle)

        # Parallel gripper with a moving finger gap, rather than a decorative
        # claw that stays fixed when IO9 is adjusted.
        ux, uy = math.cos(hand_angle), math.sin(hand_angle)
        nx, ny = -uy, ux

        def hand_point(along, across):
            return (hand_end[0]+ux*along+nx*across,
                    hand_end[1]+uy*along+ny*across)

        gap = 6 + opening*15
        polygon((hand_point(-11, -25), hand_point(9, -25),
                 hand_point(9, 25), hand_point(-11, 25)), '#3f5069', '#8492a7')
        line((hand_point(1, -20), hand_point(1, 20)), '#152237', 4)
        for side in (-1, 1):
            finger = (hand_point(2, side*(gap+8)), hand_point(35, side*(gap+8)),
                      hand_point(43, side*(gap-1)), hand_point(35, side*(gap-4)),
                      hand_point(28, side*(gap+1)), hand_point(2, side*(gap+1)))
            polygon([(x+4, y+5) for x, y in finger], '#0d1829')
            polygon(finger, '#7a879b', '#bac4d2')
            line((hand_point(27, side*(gap+1)), hand_point(35, side*(gap-4))),
                 '#151f30', 4)
            ellipse(*hand_point(3, side*(gap+4)), 3, 3, '#222f43', self.ACCENTS[3])
        ellipse(*hand_point(-2, 0), 4, 4, self.ACCENTS[3])

        # Four thin annotation leaders match the controller's channel colours.
        annotations = (
            (6, (272, 372), (112, 351), self.ACCENTS[0], 'Rotation'),
            (7, (joint[0]-22, joint[1]-15), (108, 146), self.ACCENTS[1], 'Elbow'),
            (8, (end[0]+9, end[1]-23), (589, 109), self.ACCENTS[2], 'Wrist'),
            (9, hand_point(15, -gap-12), (612, 261), self.ACCENTS[3], 'Claw'),
        )
        for pin, start, label, accent, name in annotations:
            x, y = label
            on_left = x < 300
            label_item = text(x, y, f'IO{pin}  {name}', accent, 10, bold=True)
            label_bounds = self.bbox(label_item)
            label_width = ((label_bounds[2]-label_bounds[0])/scale
                           if label_bounds else 100.0)
            endpoint = (x+label_width+12 if on_left else x-12, y)
            midpoint = ((start[0]+endpoint[0])/2, endpoint[1])
            line((start, midpoint, endpoint), '#495b78')
            ellipse(*start, 2, 2, accent)
