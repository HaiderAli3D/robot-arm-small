# Technical reference

[Back to README](../README.md) | [Keyboard console guide](keyboard-only.md) | [Camera and hardware setup](setup.md)

These are the current controller details. Run the commands below from the repository root after setup. The [verification notes](verification.md) and [original implementation plan](implementation-plan.md) contain historical configurations that have since changed.

The keyboard-only console uses the same USB protocol and firmware. Its controls and schematic are covered in the [keyboard guide](keyboard-only.md); the gesture mapping and `config.toml` settings below apply to the camera-tracking app. Changing tracking gains or smoothing does not change keyboard movement.

## Coordinates and calibration

Channels are ordered GPIO6 (left-hand rotation), GPIO7 (right elbow), GPIO8 (right wrist), and GPIO9 (right pinch). Displayed position equals raw command minus the saved servo zero. Before calibration, each zero is raw 90. Boot sets all four channels to raw 90; the reference assembly assumes a straight arm and open claw there.

C captures each current commanded position and its corresponding gesture after a four-second countdown. Servos remain powered, targets stay unchanged, and any complete detected pose is accepted. Subsequent movement is relative to these paired references, including a partially pinched claw. Keyboard positions and `Session.set_position()` use the same zeros. These are commanded positions, not shaft feedback: the app cannot measure a position set by moving an unpowered servo by hand.

## Settings

The CLI loads [config.toml](../config.toml) by default. Restart after edits, or pass `--config path\to\settings.toml` for another file. Programmatic `Config()` defaults can differ from the supplied file.

| Setting | Supplied value | Meaning |
|---|---|---|
| `camera` | `1` | Startup camera; V probes indices 0-3 |
| `width`, `height` | `960`, `720` | Software downscaling bounds; native capture format retained |
| `confidence` | `0.4` | Pose detection, presence, tracking, and landmark gating |
| `hand_confidence` | `0.2` | Hand detection, presence, and tracking thresholds |
| `send_hz` | `30` | Periodic tracking command cadence |
| `smoothing_tau` | `2.0` | Exponential tracking-filter time constant in seconds |
| `deadband` | `1.0` | Ignore target changes within this many nominal degrees |
| IO6 / IO7 / IO8 `gain` | `4` | Relative angular gesture response |
| IO9 `gain` | `5` | Relative pinch closure response |
| Each joint's `direction` | `1` | Use `-1` to reverse gesture response |

Keyboard commands are direct seven-degree increments, independent of gain, direction, and tracking smoothing. On Windows, repeat runs at 1.5 times the configured keyboard rate, starting one repeat interval after a press. Due increments are combined per channel per frame. Release, focus loss, Space, C, and M end an existing hold. Other operating systems retain OpenCV's normal key repeat; the complete setup has been tested on Windows.

Hand ownership uses same-frame pose wrists rather than hand result order or handedness labels. Clear matches within 18% of the image diagonal are accepted; ambiguous matches are omitted. Each control validates only its required landmarks, so an invalid pinch fingertip can leave wrist control available. Lower confidence settings admit more detections and potentially less reliable ones; MediaPipe's presence and tracking thresholds also influence re-detection. See the [official options](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python#configuration_options).

## Wiring and mechanical calibration

Use positional servos such as the existing sketch's MG90S. Continuous-rotation servos interpret pulses as speed/direction and cannot be controlled as joints by this program.

- Connect the four signal wires to GPIO6, GPIO7, GPIO8, and GPIO9 as above.
- Power the servos from an appropriately sized regulated 5V supply and connect its ground to ESP32 ground. Do not power four servos from GPIO or assume the board's 5V pin can supply them.
- Keep the external servo +5V rail separate from the laptop/board USB +5V rail.
- GPIO7 is also a reset-time JTAG strapping pin on ESP32-C5; avoid external circuitry that forces its reset level. It operates as a normal PWM output after boot.

The 50Hz, 14-bit PWM retains the linear mapping `pulse_us = 1000 + raw_angle * 1000 / 180`, extending past the old 1000..2000 microsecond envelope. For example, raw -90 and 270 request 500 and 2500 microseconds. Raw 90 remains physical centre; calibration changes the displayed zero, not this pulse formula. The only output saturation is the electrical duty register's representable range, 0..16383; negative pulse widths and pulses longer than a PWM period cannot be produced. Extreme requested positions may therefore share the same output. Neither requested degrees nor pulse widths establish a servo's actual mechanical travel.

`direction` reverses a tracking control and `gain` scales it. The `minimum` and `maximum` joint settings have been removed. GPIO9 defaults to raw `claw_open=90`, `claw_closed=0`; these are mapping reference points rather than enforced travel endpoints. Pinch closure is thumb/index separation divided by palm width, normalized between `pinch_open_ratio=1.0` and `pinch_closed_ratio=0.2`. Closure itself stays between 0 and 1. GPIO9 moves according to the change in normalized closure from calibration. With `gain=5` and an open-hand reference (ratio 1.0), ratios 1.0, 0.96, 0.92, and 0.2 request positions 0, -22.5, -45, and -450 relative to the captured servo position. These are nominal commanded values, not additional physical travel. A pinched reference shifts those relative targets so the captured pinch always means zero movement.

The serial protocol, `claw_open`, and `claw_closed` retain the raw coordinate offset (90 = centre); UI positions and `Session.set_position(pin, position, now)` are signed about each servo's saved calibration zero. Commands use signed 32-bit integers, rounded to the nearest nominal degree. The finite-number and integer-encoding checks remain; there are no configured joint travel limits or speed caps. Firmware applies each target on its next 50Hz output tick. Tracking uses `smoothing_tau = 2.0`: all four controls ease toward their targets with a two-second time constant, reaching about 63% of a sustained change after two seconds and 95% after six seconds. This adds no initial delay; keyboard steps remain immediate. `deadband` filters small tracking changes. GPIO7 controls elbow bend and GPIO8 controls wrist bend.

## Loss of tracking, pause, and reconnect

A missing control keeps its last target while any visible controls continue updating. Running stays selected indefinitely, and returning tracking updates the targets immediately. Camera stalls and old frame timestamps do not pause the app. The firmware has no inactivity watchdog: it retains its last target and continues accepting poses without another resume command.

On USB failure, the app retains your reference and run/pause choice. Press **R** to reconnect; if running was selected, control continues automatically. Reconnecting may reboot/recenter the board. Space explicitly pauses and holds the current output. Q/Escape and closing the window also stop the application. Basic command syntax, finite-number checks, and integer-encoding checks remain.

Quit and pause are software holds, not electrical emergency stops. `off` stops pulses and can release holding torque while power remains connected. Disconnect servo power when necessary for mechanical work.

## Diagnostics and developer commands

```powershell
# Close the app, then inspect cameras (never opens serial ports)
.\.venv\Scripts\python.exe -m arm_control --list-cameras

# Preview with a different camera
.\.venv\Scripts\python.exe -m arm_control --dry-run --camera 1

# Bounded real-camera/model smoke test; never drives hardware
.\.venv\Scripts\python.exe -m arm_control --dry-run --headless --frames 60

# Python tests only
.\.venv\Scripts\python.exe -m unittest discover -s tests

# Python and native firmware tests (expects C:\mingw64\bin\g++.exe)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1

# Native firmware tests with another compiler location
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-firmware.ps1 -Compiler 'C:\path\to\g++.exe'

# Compile the ESP32-C5 sketch; does not upload it
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-firmware.ps1
```

The firmware build helper requires the Espressif board package installed during [setup](setup.md); version 3.3.10 was tested. It finds Arduino CLI on PATH or in Arduino IDE's standard installation folder. Pass `-ArduinoCli 'C:\path\to\arduino-cli.exe'` if yours is elsewhere. Build output goes into the ignored `build/esp32c5-tracking` folder.

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
| `off` | Stops servo pulses and leaves tracking mode; servo power remains connected |
| Invalid command | `ERR reason`; valid tracking remains enabled |

The tracking sketch includes **absolute-angle** manual commands: `1 90`, `2 45`, `3 120`, `4 60`, `all 90`, `1 off`, `off`, and `help`. Thus `1 90` means center; it does not add 90 degrees. Extended examples: `1 -90` requests -180 from physical centre and `1 270` requests +180 from physical centre; these raw firmware commands do not use the app's calibration zeros. The preserved `RELATIVE-CW-v4` sample instead uses signed relative increments and `center`/`status`. These are separate firmware programs. Manual moves and off commands explicitly leave tracking mode; `help` does not. Targets apply directly without repeated heartbeats. Use manual commands with the app disconnected. After `off`, `resume` alone leaves pulses disabled; an accepted pose enables the outputs again.

See [verification notes](verification.md) for actual tests and remaining hardware checks.

## Sources

- [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Espressif Arduino LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
- [ESP32-C5 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf)
- [Waveshare board documentation](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX)
