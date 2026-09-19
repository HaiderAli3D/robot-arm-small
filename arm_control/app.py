"""Small OpenCV desktop UI. All motion is mediated by Session."""

import json
import statistics
import textwrap
import time
import traceback

from .control import Observation
from .session import Session

WINDOW = 'Robot arm - MediaPipe'
MISSING = Observation(None, None, None, None)
SERVO_KEYS = {
    ord('w'): (6,-5), ord('e'): (6,5),
    ord('t'): (7,-5), ord('y'): (7,5),
    ord('u'): (8,-5), ord('i'): (8,5),
    ord('p'): (9,-5), ord('['): (9,5),
}
HAND_EDGES = ((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
              (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
              (13,17),(0,17),(17,18),(18,19),(19,20))


def list_cameras():
    from .camera import Camera
    found = False
    for index in range(4):
        camera = Camera(index, 640, 480).start()
        try:
            frame = camera.latest(timeout=3)
            if frame is not None:
                h, w = frame.image.shape[:2]
                print(f'Camera {index}: {w}x{h}')
                found = True
        finally:
            camera.close()
    if not found:
        print('No camera found at indices 0..3. Check Windows camera permissions and other camera apps.')


def _display(frame, pose, hands, matches, observation, session, inference_ms, frame_age, camera_status):
    import cv2
    display = cv2.flip(frame, 1)
    height, width = display.shape[:2]

    def xy(p):
        return round((1-p.x)*(width-1)), round(p.y*(height-1))

    if pose is not None and pose.pose_landmarks:
        points = pose.pose_landmarks[0]
        for a, b in ((11,13),(13,15),(12,14),(14,16)):
            if min(points[a].visibility or 0, points[b].visibility or 0) >= session.config.confidence:
                cv2.line(display, xy(points[a]), xy(points[b]), (190,190,190), 3)
    if hands is not None:
        for side, index in matches.items():
            color = (90,220,140) if side == 'right' else (240,190,85)
            points = hands.hand_landmarks[index]
            for a, b in HAND_EDGES:
                cv2.line(display, xy(points[a]), xy(points[b]), color, 2)
            for point in points:
                cv2.circle(display, xy(point), 3, color, -1)
            label = 'Right: wrist / claw' if side == 'right' else 'Left: rotation'
            cv2.putText(display, label, xy(points[0]), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1, cv2.LINE_AA)
    if width != 960:
        display = cv2.resize(display, (960, round(height*960/width)))
    width = display.shape[1]
    panel = cv2.copyMakeBorder(display, 0, 330, 0, 0, cv2.BORDER_CONSTANT, value=(25,28,28))
    top = display.shape[0]
    controller = session.controller
    if controller.active:
        if session.link is None:
            state = 'RUNNING - preview only'
        elif not session.connected:
            state = 'RUNNING - USB disconnected'
        elif session.control_mode == 'keyboard':
            state = 'RUNNING - keyboard control'
        elif controller.calibrating:
            state = 'RUNNING - setting reference'
        else:
            state = 'RUNNING - SPACE to pause'
        color = (100,220,100)
    elif controller.calibrating:
        state, color = 'CALIBRATING - arm held', (220,155,65)
    elif session.link is None:
        state, color = 'PREVIEW - servos disconnected', (175,175,175)
    else:
        state, color = 'PAUSED - arm held', (60,190,245)
    cv2.rectangle(panel, (0,top), (width,top+52), color, -1)
    cv2.putText(panel, state, (14,top+36), cv2.FONT_HERSHEY_SIMPLEX, .85,
                (15,25,20), 2, cv2.LINE_AA)
    y = top + 79
    for part in textwrap.wrap(controller.status, 76):
        cv2.putText(panel, part, (14,y), cv2.FONT_HERSHEY_SIMPLEX, .67,
                    (245,245,245), 2, cv2.LINE_AA)
        y += 29
    angles = '   '.join(f'IO{pin} {value:+6.1f}' for pin,value in zip(range(6,10),controller.positions))
    inputs = '  '.join(f'{label}: {value:.1f}' if value is not None else f'{label}: missing'
                       for label,value in zip(('IO6 rotation','IO7 elbow','IO8 wrist','IO9 pinch'),
                                              (observation.rotation,observation.elbow,observation.wrist,observation.pinch)))
    lines = [f'Positions (from zero): {angles}', session.connection_status,
             inputs,
             f'{camera_status} | inference {inference_ms:.0f} ms | frame age {frame_age*1000:.0f} ms',
             'C calibrate   SPACE start/pause   V switch camera   R reconnect   Q / ESC quit',
             'Keys -/+ 5deg: W/E IO6   T/Y IO7   U/I IO8   P/[ IO9   M tracking',
             f'Control: {session.control_mode}. Servo keys select keyboard control and move immediately.']
    for line in lines:
        for part in textwrap.wrap(line, max(70, int(width/8.2))):
            cv2.putText(panel, part, (14,y), cv2.FONT_HERSHEY_SIMPLEX, .52, (225,235,230), 1, cv2.LINE_AA)
            y += 23
    return panel


def run(config, args):
    import cv2
    import numpy as np
    from .camera import Camera
    from .camera_switch import CameraSwitcher
    from .transport import SerialLink
    from .vision import Tracker

    session = Session(config, None if args.dry_run else SerialLink(args.port))
    camera = tracker = None
    selector = None
    camera_failed = False
    placeholder = np.zeros((config.height,config.width,3),dtype=np.uint8)
    processed = valid_frames = 0
    latencies = []
    frame = pose = hands = None
    matches = {}
    sequence = -1
    started = time.monotonic()
    last_capture = started
    inference_ms = 0.0
    observation = MISSING
    camera_status = 'Starting camera'
    tracker_error = None
    try:
        tracker = Tracker(config, args.models)
        camera = Camera(config.camera, config.width, config.height).start()
        selector = CameraSwitcher(camera,config.camera,config.width,config.height,camera_factory=Camera)
        if session.link:
            session.connect()
        if not args.headless:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW, config.width, config.height+330)
        while True:
            was_switching = selector.switching
            changed = selector.poll()
            scan_finished = was_switching and not selector.switching
            if changed:
                camera = selector.camera
                sequence = -1
                last_capture = time.monotonic()
                camera_failed = False
                frame = pose = hands = None
                matches = {}
                observation = MISSING
            if changed or (scan_finished and tracker is None):
                # Detach before closing: a failed replacement must never leave
                # a closed model owned by the loop or by final cleanup.
                previous_tracker, tracker = tracker, None
                try:
                    if previous_tracker is not None:
                        previous_tracker.close()
                    tracker = Tracker(config,args.models)
                    tracker_error = None
                except Exception as error:
                    tracker_error = f'Tracking unavailable - press V to retry: {error}'
                    traceback.print_exc()
            captured = None if selector.switching else camera.latest(after=sequence, timeout=.03)
            now = time.monotonic()
            unavailable = captured is None and (camera.error or (now-last_capture > (10 if frame is None else 2)))
            if selector.switching:
                camera_status = selector.status
            elif unavailable:
                if args.headless:
                    raise RuntimeError(f'Camera: {camera.error or "stopped delivering frames"}')
                if not camera_failed:
                    session.prepare_camera_switch()
                    camera_failed = True
                frame = pose = hands = None
                matches = {}
                observation = MISSING
                camera_status = f'Camera {selector.index} unavailable - press V to switch camera'
            elif captured is not None:
                camera_failed = False
                sequence, last_capture, frame = captured.sequence, captured.captured_at, captured.image
                camera_status = selector.status
                if tracker is None:
                    pose = hands = None
                    matches = {}
                    observation = MISSING
                    inference_ms = 0
                    session.camera_missing(now)
                else:
                    inference_start = time.monotonic()
                    observation, matches, pose, hands = tracker.process(frame, last_capture)
                    now = time.monotonic()
                    inference_ms = (now-inference_start)*1000
                    latencies.append(inference_ms)
                    processed += 1
                    valid_frames += int(all(value is not None for value in (
                        observation.rotation, observation.elbow, observation.wrist, observation.pinch)))
                    session.frame(observation, captured_at=last_capture, now=now)
            elif not camera_failed and now-last_capture > .15:
                camera_status = 'Waiting for camera frames'
                observation = MISSING
                session.camera_missing(now)
            if tracker_error and not selector.switching and not unavailable:
                camera_status = tracker_error
            if not args.headless:
                cv2.imshow(WINDOW, _display(placeholder if frame is None else frame,
                                           pose, hands, matches, observation, session, inference_ms,
                                           now-last_capture, camera_status))
            key = -1 if args.headless else cv2.waitKey(1) & 0xFF
            if not args.headless and cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key in (27, ord('q'), ord('Q')):
                break
            lower_key = key + 32 if ord('A') <= key <= ord('Z') else key
            if lower_key in SERVO_KEYS:
                pin, delta = SERVO_KEYS[lower_key]
                session.nudge(pin,delta,time.monotonic())
            elif key in (ord('m'),ord('M')):
                session.use_tracking(time.monotonic())
            elif key in (ord('v'),ord('V')) and not selector.switching:
                session.prepare_camera_switch()
                selector.request_next()
                # Keep the last preview visible while probes run, but never
                # display or apply its stale landmarks as new observations.
                pose = hands = None
                matches = {}
                observation = MISSING
                inference_ms = 0
            elif key in (ord('c'), ord('C')):
                session.calibrate(time.monotonic())
            elif key == 32:
                if session.controller.active:
                    session.pause()
                else:
                    session.resume(time.monotonic())
            elif key in (ord('r'), ord('R')) and session.link:
                session.connect()
            if args.frames and processed >= args.frames:
                break
            if args.headless and captured is None:
                time.sleep(.005)
        elapsed = time.monotonic()-started
        print(json.dumps({'mode': 'dry-run' if args.dry_run else 'live', 'frames': processed,
                          'fully_tracked_frames': valid_frames, 'elapsed_seconds': round(elapsed,2),
                          'mean_inference_ms': round(statistics.mean(latencies),2) if latencies else None,
                          'median_inference_ms': round(statistics.median(latencies),2) if latencies else None}))
        return 0
    finally:
        # Freeze firmware before releasing camera/model resources, even on exceptions.
        try:
            session.close()
        finally:
            try:
                if selector:
                    selector.close()
                elif camera:
                    camera.close()
            finally:
                try:
                    if tracker:
                        tracker.close()
                finally:
                    if not args.headless:
                        cv2.destroyAllWindows()
