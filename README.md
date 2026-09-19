# Camera-controlled ESP32-C5 robot arm

Track your arms and hands locally with MediaPipe, then send four servo positions over USB UART. The laptop does the tracking; the ESP32 generates the servo pulses. No cloud service, Wi-Fi connection, or video recording is used.

| Servo signal | Control | Neutral |
|---|---|---|
| GPIO6 | Left hand turning like a clock hand in the camera preview | 0 degrees at captured reference |
| GPIO7 | Right elbow bending | 0 degrees at captured reference |
| GPIO8 | Right wrist bending relative to the forearm | 0 degrees at captured reference |
| GPIO9 | Right thumb/index pinch | 0 degrees at captured reference |

The app displays **signed positions relative to the latest calibrated position**, without the old -90/+90 travel cap. Keyboard and tracking targets may exceed those values on every servo. Calibration makes each servo's current position its own zero without moving it. Protocol 2 uses raw position = displayed position + that servo's saved zero angle. Before calibration, the zero angles are 90. Boot centres all channels (displayed 0); the linkages are assumed aligned for a straight arm and open claw there. Displayed values are requested positions, not measured shaft angles. The servo's mechanical travel is unchanged. The user's `RELATIVE-CW-v4` sample remains unchanged under `ESP32C5_FourServos`; the app uses the separate `ESP32C5_Tracking` sketch.

## Quick start on this laptop

Python 3.12 and Arduino ESP32 core 3.3.10 were available during development. Run from PowerShell:

```powershell
cd C:\Projects\Robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Setup creates `.venv`, installs the locked Windows dependencies, and downloads the two official MediaPipe models. Downloads are versioned and checked against SHA-256 hashes. Subsequent tracking works offline. The default run is **preview only** and never opens a serial port.

In the preview:

Press **V** in the preview window to cycle to the next available camera. The supplied configuration starts on **camera 1 (Camo)**. The app checks camera indices 0-3, skips unavailable devices, and keeps the current camera if no alternative is found. Camera switching preserves your run/pause choice and reference pose. Camera selection applies to the current run; change `camera` in `config.toml` to set the startup default.

1. Keep one person in view, including the right shoulder, elbow, wrist, and both hands. Keep the hands apart so their arm associations are clear.
2. Choose any comfortable pose with your right arm and both hands visible. Your elbow and wrist can be bent, and your fingers can be open or pinched.
3. Optionally press **C** to choose a reference pose after a four-second countdown. There is no hold-steady test or additional capture delay. C preserves your run/pause choice and holds the last angles until capture. On capture all four displayed positions become 0; the physical targets stay where they are.
4. Press **Space** to start. If no reference exists, the first complete tracked pose supplies it automatically. Turn the left hand like a clock hand; bend the right elbow and wrist; pinch/open the right thumb and index finger.
5. Press **Space** to pause and hold, or **Q/Escape** to quit. The window's close button also stops control.

The large status banner shows your chosen mode: green **RUNNING** or amber **PAUSED**. Running remains selected through missing tracking, camera changes, calibration, and USB failures. The banner identifies disconnected USB or a pending reference separately. Blue **CALIBRATING** means you are setting a reference while paused. Space always toggles the mode, including while the camera is unavailable or switching.

### Keyboard control

Focus the preview window and use the number pad with **Num Lock on**. Each press changes the selected servo by **7 degrees**. On Windows, holding a key repeats at **1.5 times the configured keyboard repeat rate**, starting one repeat interval after the initial step with no extra hold delay. The app reads Windows' speed setting without changing it (currently 30 repeats/second on this laptop, giving 45 servo increments/second and a first repeat due after about 22 ms). Increments due between video frames are combined into one target update per channel. Actual updates follow the app's frame timing. The motor's physical maximum speed is unchanged.

| Servo | Decrease | Increase |
|---|---|---|
| IO6 | Numpad 1 | Numpad 2 |
| IO7 | Numpad 4 | Numpad 5 |
| IO8 | Numpad 7 | Numpad 8 |
| IO9 | Numpad 3 | Numpad 6 |

Pressing a servo key selects **keyboard control**, starts movement, and sends the new angle immediately. It works without hand detection or calibration. Camera gestures cannot overwrite keyboard positions. **Space** pauses/resumes; another servo key also resumes and moves. **M** selects tracking again while retaining your run/pause choice; **C** selects tracking and starts its four-second calibration countdown. After Space, M, C, or leaving the window, release and press a servo key again to start a new hold. Reconnecting retains keyboard mode. Keyboard steps are direct servo degrees, independent of tracking gain and direction, with no joint travel clipping. Matching number-row digits also work. The previous letter-based servo bindings are replaced. Other operating systems retain their normal key repeat through OpenCV.

Calibration records the current servo commands and your left-hand rotation, right-elbow bend, right-wrist bend, and pinch as paired zero points. Any detected pose is accepted. Keeping the captured pose keeps all four servos at their current positions, including the claw. Later gesture changes move relative to those positions. Calibrating again replaces all four zeros with the latest positions; it does not send the arm back to centre. Keyboard steps and `Session.set_position` use the same saved zeros. Run/pause selection is preserved.

GPIO7 elbow and GPIO8 wrist sensitivity are **4x**: a 5-degree change from your reference requests a 20-degree servo change before optional smoothing. GPIO6 retains 1x gain and the claw retains 2x. Keyboard steps are 7 servo degrees. Rotating the whole right forearm without bending the wrist does not change the wrist's relative angle.

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

Replace `COM9` with the actual USB UART port; Bluetooth COM ports are not the robot. Opening a UART may reset the board and center the servos. The app waits for startup, performs a versioned handshake, and initially stays paused until Space. A reconnect restores the previously selected run/pause state. This app requires protocol 2 firmware: upload the current tracking sketch before restarting live control. Protocol 1 firmware rejects extended positions and is incompatible with this app.

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

The 50Hz, 14-bit PWM retains the linear mapping `pulse_us = 1000 + raw_angle * 1000 / 180`, extending past the old 1000..2000 microsecond envelope. For example, raw -90 and 270 request 500 and 2500 microseconds. Raw 90 remains physical centre; calibration changes the displayed zero, not this pulse formula. The only output saturation is the electrical duty register's representable range, 0..16383; negative pulse widths and pulses longer than a PWM period cannot be produced. Extreme requested positions may therefore share the same output. Neither requested degrees nor pulse widths establish a servo's actual mechanical travel.

`direction` reverses a tracking control and `gain` scales it. The `minimum` and `maximum` joint settings have been removed. GPIO9 defaults to raw `claw_open=90`, `claw_closed=0`; these are mapping reference points rather than enforced travel endpoints. Pinch closure is thumb/index separation divided by palm width, normalized between `pinch_open_ratio=1.0` and `pinch_closed_ratio=0.2`. Closure itself stays between 0 and 1. GPIO9 moves according to the change in normalized closure from calibration. With `gain=2` and an open-hand reference (ratio 1.0), ratios 1.0, 0.8, 0.6, and 0.2 request positions 0, -45, -90, and -180 relative to the captured servo position. A pinched reference shifts those relative targets so the captured pinch always means zero movement.

The serial protocol, `claw_open`, and `claw_closed` retain the raw coordinate offset (90 = centre); UI positions and `Session.set_position(pin, position, now)` are signed about each servo's saved calibration zero. Commands use signed 32-bit integers, rounded to the nearest nominal degree. The finite-number and integer-encoding checks remain; there are no configured joint travel limits or speed caps. Firmware applies each target on its next 50Hz output tick. Optional `smoothing_tau` and `deadband` filter tracking jitter. GPIO7 controls elbow bend and GPIO8 controls wrist bend.

## Loss of tracking, pause, and reconnect

A missing control keeps its last target while any visible controls continue updating. Running stays selected indefinitely, and returning tracking updates the targets immediately. Camera stalls and old frame timestamps do not pause the app. The firmware has no inactivity watchdog: it retains its last target and continues accepting poses without another resume command.

On USB failure, the app retains your reference and run/pause choice. Press **R** to reconnect; if running was selected, control continues automatically. Reconnecting may reboot/recenter the board. Space explicitly pauses and holds the current output. Q/Escape and closing the window also stop the application. Basic command syntax, finite-number checks, and integer-encoding checks remain.

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

If the camera cannot open, press **V** in the window, check Windows **Privacy & security > Camera**, allow desktop apps, or close competing camera apps. The shortcut remains available even when the current camera has no feed. If your only camera failed to open, fix its permissions or competing app, then restart this app to retry it. Camo/virtual cameras may be different indices from the integrated webcam. Cameras open in their native format, using Windows Media Foundation first and DirectShow if it cannot open. The app downsizes frames in software to fit `width` and `height`, preserving aspect ratio; it does not force Camo to accept an unsupported capture size. Models run on the CPU; reduce those processing dimensions if tracking feels delayed. The app retains only the latest captured frame to avoid a growing camera queue. Normal MediaPipe native-library warnings may appear on stderr.

`requirements.txt` lists direct dependencies; `requirements-lock.txt` records the complete tested Python 3.12 Windows environment. Only one OpenCV package is installed. The reference pose and servo zeros are kept in memory across camera changes and reconnects; restarting the app clears them. Editing config requires restarting the app.

## Serial protocol and manual controls

115200 baud, ASCII newline-delimited, protocol version 2. All four pose angles are integers in **GPIO6, GPIO7, GPIO8, GPIO9** order. A whole pose is rejected if any field is invalid. Only one command is in flight at once.

| Command | Response / effect |
|---|---|
| `hello` | `ROBOT_ARM 2 a6 a7 a8 a9`; freezes and pauses |
| `resume` | `OK resume`; allows tracking updates |
| `pose 90 100 80 50` | `OK pose`; sets all four targets |
| `hold` | `OK hold a6 a7 a8 a9`; freezes current outputs |
| Invalid command | `ERR reason`; valid tracking remains enabled |

The tracking sketch includes **absolute-angle** manual commands: `1 90`, `2 45`, `3 120`, `4 60`, `all 90`, `1 off`, `off`, and `help`. Thus `1 90` means center; it does not add 90 degrees. Extended examples: `1 -90` requests -180 from physical centre and `1 270` requests +180 from physical centre; these raw firmware commands do not use the app's calibration zeros. Your preserved `RELATIVE-CW-v4` sample instead uses signed relative increments and `center`/`status`. These are separate firmware programs. Manual moves and off commands explicitly leave tracking mode; `help` does not. Targets apply directly without repeated heartbeats. Use manual commands with the app disconnected. After `off`, `resume` alone leaves pulses disabled; an accepted pose enables the outputs again.

See [verification notes](docs/verification.md) for actual tests and remaining hardware checks.

## Sources

- [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Espressif Arduino LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
- [ESP32-C5 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf)
- [Waveshare board documentation](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX)
