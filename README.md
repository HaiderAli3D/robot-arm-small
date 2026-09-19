# Camera-controlled ESP32-C5 robot arm

Track your arms and hands locally with MediaPipe, then send four servo positions over USB UART. The laptop does the tracking; the ESP32 generates the servo pulses. No cloud service, Wi-Fi connection, or video recording is used.

| Servo signal | Control | Neutral |
|---|---|---|
| GPIO6 | Left hand turning like a clock hand in the camera preview | 0 degrees at captured reference |
| GPIO7 | Right elbow bending | 0 degrees at captured reference |
| GPIO8 | Right wrist bending relative to the forearm | 0 degrees at captured reference |
| GPIO9 | Right thumb/index pinch | 0 degrees open, -90 degrees closed |

The app displays **signed positions from -90 to +90 degrees**, with 0 at servo centre. Firmware still uses its existing 0..180 commands: signed position + 90 = firmware angle. Boot centres all channels (displayed 0); the linkages are assumed aligned for a straight arm and open claw there. There are no joint-position sensors: displayed values are commands, not measured mechanical feedback. This coordinate change does not extend the servos' physical travel. The user's `RELATIVE-CW-v4` sample remains unchanged under `ESP32C5_FourServos`; the app uses the separate `ESP32C5_Tracking` sketch.

## Quick start on this laptop

Python 3.12 and Arduino ESP32 core 3.3.10 were available during development. Run from PowerShell:

```powershell
cd C:\Projects\Robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Setup creates `.venv`, installs the locked Windows dependencies, and downloads the two official MediaPipe models. Downloads are versioned and checked against SHA-256 hashes. Subsequent tracking works offline. The default run is **preview only** and never opens a serial port.

In the preview:

Press **V** in the preview window to cycle to the next available camera. The app checks camera indices 0-3, skips unavailable devices, and keeps the current camera if no alternative is found. Camera switching preserves your run/pause choice and reference pose. Camera selection applies to the current run; change `camera` in `config.toml` to set the startup default.

1. Keep one person in view, including the right shoulder, elbow, wrist, and both hands. Keep the hands apart so their arm associations are clear.
2. Choose any comfortable pose with your right arm and both hands visible. Your elbow and wrist can be bent, and your fingers can be open or pinched.
3. Optionally press **C** to choose a reference pose after a four-second countdown. There is no hold-steady test or additional capture delay. C preserves your run/pause choice and holds the last angles until the new reference is captured.
4. Press **Space** to start. If no reference exists, the first complete tracked pose supplies it automatically. Turn the left hand like a clock hand; bend the right elbow and wrist; pinch/open the right thumb and index finger.
5. Press **Space** to pause and hold, or **Q/Escape** to quit. The window's close button also stops control.

The large status banner shows your chosen mode: green **RUNNING** or amber **PAUSED**. Running remains selected through missing tracking, camera changes, calibration, and USB failures. The banner identifies disconnected USB or a pending reference separately. Blue **CALIBRATING** means you are setting a reference while paused. Space always toggles the mode, including while the camera is unavailable or switching.

### Keyboard control

Focus the preview window and use these keys. Each press changes the selected servo by **5 degrees**; holding a key uses your keyboard's normal repeat rate.

| Servo | Decrease | Increase |
|---|---|---|
| IO6 | W | E |
| IO7 | T | Y |
| IO8 | U | I |
| IO9 | P | [ |

Pressing a servo key selects **keyboard control**, starts movement, and sends the new angle immediately. It works without hand detection or calibration. Camera gestures cannot overwrite keyboard positions. **Space** pauses/resumes; another servo key also resumes and moves. **M** selects tracking again while retaining your run/pause choice; **C** selects tracking and starts its four-second calibration countdown. Reconnecting retains keyboard mode. Keyboard steps are direct servo degrees, independent of tracking gain and direction, within the configured joint ranges. Uppercase letters work too.

Calibration records left-hand rotation, right-elbow bend, and right-wrist bend as software zero points for GPIO6, GPIO7, and GPIO8. Any detected pose is accepted. A new reference takes effect automatically if running, or waits for Space if paused. Rotating the whole right forearm without bending the wrist does not change the wrist's relative angle. Claw control uses absolute pinch separation independently of the reference.

If calibration waits after the countdown, the instruction beneath the banner identifies a hand or joint the camera cannot currently track. Keep your right arm and both hands visible and apart. Missing or invalid tracking cannot supply a reference angle; your actual pose is never rejected for being bent or pinched.

Hand sensitivity is set separately with `hand_confidence = 0.35` in `config.toml` (previously 0.6). Lower thresholds make detection more permissive and can also admit less reliable detections. The settings control MediaPipe's detection, presence, and tracking thresholds; see the [official Hand Landmarker options](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python#configuration_options). Pose confidence remains 0.6. Left/right ownership comes from the arm positions, so uncertain handedness labels no longer discard otherwise usable hands. A 5% image-edge margin tolerates slightly clipped fingertips while keeping the wrist inside the image.

## Firmware and USB

The original sketch identifies a **Waveshare ESP32-C5-WIFI6-KIT-N16R4**. Use the USB-C connector labelled **UART**, and close Arduino Serial Monitor before running the app.

1. Open **`ESP32C5_Tracking/ESP32C5_Tracking.ino`** in Arduino IDE. The sample under `ESP32C5_FourServos` does not implement the tracking protocol.
2. Select **ESP32C5 Dev Module** from Espressif's ESP32 board package; tested with **3.3.10**.
3. Set **USB CDC On Boot: Disabled**, select the board's COM port, and upload the sketch yourself when the arm is ready to center.
4. Find the port and start live control:

```powershell
.\.venv\Scripts\python.exe -m arm_control --list-ports
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Port COM9
```

Replace `COM9` with the actual USB UART port; Bluetooth COM ports are not the robot. Opening a UART may reset the board and center the servos. The app waits for startup, performs a versioned handshake, and initially stays paused until Space. A reconnect restores the previously selected run/pause state. Upload the current tracking firmware to remove the older firmware's automatic timeout.

To compile without uploading:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-firmware.ps1
```

## Wiring and mechanical calibration

Use positional servos such as the existing sketch's MG90S. Continuous-rotation servos interpret pulses as speed/direction and cannot be controlled as joints by this program.

- Connect the four signal wires to GPIO6, GPIO7, GPIO8, and GPIO9 as above.
- Power the servos from an appropriately sized regulated 5V supply and connect its ground to ESP32 ground. Do not power four servos from GPIO or assume the board's 5V pin can supply them.
- Keep the external servo +5V rail separate from the laptop/board USB +5V rail.
- GPIO7 is also a reset-time JTAG strapping pin on ESP32-C5; avoid external circuitry that forces its reset level. It operates as a normal PWM output after boot.

The retained 50Hz, 14-bit PWM maps nominal 0..180 degrees to 1000..2000 microseconds. **Verify mechanical endpoints and direction before loading the arm.** Begin around 90 with small manual moves, then set `minimum`, `maximum`, `direction`, and `gain` in `config.toml`. For example, limit a joint to 60..120 for initial testing. The configured interval must contain 90.

GPIO9 defaults to open=90, closed=0. Set `claw_closed` to the tested closed position (including 180 if that matches your linkage) and keep it inside GPIO9's limits. Pinch closure is proportional to thumb/index separation divided by palm width: `pinch_closed_ratio = 0.2` sets fully closed and `pinch_open_ratio = 1.0` sets fully open. These thresholds are independent of calibration and can be adjusted for your hand. Calibrating with pinched fingers is valid; once you press Space the claw follows your pinch. Do not reverse both the claw endpoint and its direction unless you intend that combined effect.

The supplied configuration sets `[joints.gpio9] gain = 2` for twice the claw response. In signed display coordinates, a pinch ratio of 0.8 commands -45 degrees, 0.6 commands fully closed at -90, and 1.0 or higher opens to 0. GPIO7 controls elbow bend and GPIO8 controls wrist bend.

The servo protocol and the `minimum`, `maximum`, `claw_open`, and `claw_closed` configuration values remain in raw 0..180 coordinates. UI positions and `Session.set_position(pin, position, now)` use signed -90..90 coordinates. There is no firmware or app speed cap; firmware applies each target on its next 50Hz output tick. Optional `smoothing_tau` and `deadband` filter tracking jitter. Narrower configured joint ranges apply to tracking and keyboard commands. The obsolete `max_speed` and `loss_timeout` settings have been removed.

## Loss of tracking, pause, and reconnect

A missing control keeps its last target while any visible controls continue updating. Running stays selected indefinitely, and returning tracking updates the targets immediately. Camera stalls and old frame timestamps do not pause the app. The firmware has no inactivity watchdog: it retains its last target and continues accepting poses without another resume command.

On USB failure, the app retains your reference and run/pause choice. Press **R** to reconnect; if running was selected, control continues automatically. Reconnecting may reboot/recenter the board. Space explicitly pauses and holds the current output. Q/Escape and closing the window also stop the application. Basic command syntax, finite-number checks, and supported servo-angle bounds remain.

Quit and pause are software holds, not electrical emergency stops. `off` stops pulses and can release holding torque while power remains connected. Disconnect servo power when necessary for mechanical work.

## Settings and diagnostics

```powershell
# Inspect cameras (opens camera devices briefly, never serial ports)
.\.venv\Scripts\python.exe -m arm_control --list-cameras

# Preview with a different camera
.\.venv\Scripts\python.exe -m arm_control --dry-run --camera 1

# Bounded real-camera/model smoke test; never drives hardware
.\.venv\Scripts\python.exe -m arm_control --dry-run --headless --frames 60

# Tests (native firmware tests require g++ or an explicitly supplied compiler)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

If the camera cannot open, press **V** in the window, check Windows **Privacy & security > Camera**, allow desktop apps, or close competing camera apps. The shortcut remains available even when the current camera has no feed. If your only camera failed to open, fix its permissions or competing app, then restart this app to retry it. Camo/virtual cameras may be different indices from the integrated webcam. Models run on the CPU; reduce resolution if tracking feels delayed. The app retains only the latest captured frame to avoid a growing camera queue. Normal MediaPipe native-library warnings may appear on stderr.

`requirements.txt` lists direct dependencies; `requirements-lock.txt` records the complete tested Python 3.12 Windows environment. Only one OpenCV package is installed. The reference pose is kept in memory across camera changes and reconnects; restarting the app clears it. Editing config requires restarting the app.

## Serial protocol and manual controls

115200 baud, ASCII newline-delimited, protocol version 1. All four pose angles are integers in **GPIO6, GPIO7, GPIO8, GPIO9** order. A whole pose is rejected if any field is invalid. Only one command is in flight at once.

| Command | Response / effect |
|---|---|
| `hello` | `ROBOT_ARM 1 a6 a7 a8 a9`; freezes and pauses |
| `resume` | `OK resume`; allows tracking updates |
| `pose 90 100 80 50` | `OK pose`; sets all four targets |
| `hold` | `OK hold a6 a7 a8 a9`; freezes current outputs |
| Invalid command | `ERR reason`; valid tracking remains enabled |

The tracking sketch includes **absolute-angle** manual commands: `1 90`, `2 45`, `3 120`, `4 60`, `all 90`, `1 off`, `off`, and `help`. Thus `1 90` means center; it does not add 90 degrees. Your preserved `RELATIVE-CW-v4` sample instead uses signed relative increments and `center`/`status`. These are separate firmware programs. Manual moves and off commands explicitly leave tracking mode; `help` does not. Targets apply directly without repeated heartbeats. Use manual commands with the app disconnected. After `off`, `resume` alone leaves pulses disabled; an accepted pose enables the outputs again.

See [verification notes](docs/verification.md) for actual tests and remaining hardware checks.

## Sources

- [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Espressif Arduino LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
- [ESP32-C5 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf)
- [Waveshare board documentation](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX)
