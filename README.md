# Camera-controlled ESP32-C5 robot arm

Track your arms and hands locally with MediaPipe, then send four servo positions over USB UART. The laptop does the tracking; the ESP32 generates the servo pulses. No cloud service, Wi-Fi connection, or video recording is used.

| Servo signal | Control | Neutral |
|---|---|---|
| GPIO6 | Left hand turning like a clock hand in the camera preview | 90 degrees |
| GPIO7 | Right elbow bending | 90 degrees, arm straight |
| GPIO8 | Right hand bending relative to the forearm in the camera view | 90 degrees, wrist straight |
| GPIO9 | Right thumb/index pinch | 90 degrees, claw open |

The robot's horns/linkages must already be aligned so **90 degrees on all four channels means straight arm and open claw**. Firmware commands this pose at boot. There are no joint-position sensors: every displayed angle is a commanded pulse position, not measured mechanical feedback. The tracking firmware retains the working sample's PWM and pin assignments. Your newer `RELATIVE-CW-v4` sample remains unchanged under `ESP32C5_FourServos`; the app uses the separate `ESP32C5_Tracking` sketch.

## Quick start on this laptop

Python 3.12 and Arduino ESP32 core 3.3.10 were available during development. Run from PowerShell:

```powershell
cd C:\Projects\Robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Setup creates `.venv`, installs the locked Windows dependencies, and downloads the two official MediaPipe models. Downloads are versioned and checked against SHA-256 hashes. Subsequent tracking works offline. The default run is **preview only** and never opens a serial port.

In the preview:

Press **V** in the preview window to cycle to the next available camera. The app checks camera indices 0–3, skips unavailable devices, and keeps the current camera if no alternative is found. The window stays responsive while searching. Every switch attempt holds the arm and clears calibration; press **C**, then Space, after choosing a camera. Camera selection applies to the current run; change `camera` in `config.toml` to set the startup default.

1. Keep one person in view, including the right shoulder, elbow, wrist, and both hands. Keep the hands apart so their arm associations are clear.
2. Extend the right arm sideways so its wrist bend can be seen in the image. Keep its wrist straight and thumb/index open. Hold the left hand upright with fingers visible.
3. Press **C**, hold that pose steadily for one second, and wait for **Calibrated**.
4. Press **Space** to start. Turn the left hand like a clock hand; bend the right elbow and wrist; pinch/open the right thumb and index finger.
5. Press **Space** to pause and hold, or **Q/Escape** to quit. The window's close button also stops control.

Calibration allows up to 20 degrees of elbow/wrist departure from straight, but requires a steady pose. Large movement restarts the one-second capture. Input angles and tracking status help diagnose a missing or unstable control. Rotating the whole right forearm without bending the wrist does not change the wrist's relative angle.

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

Replace `COM9` with the actual USB UART port; Bluetooth COM ports are not the robot. Opening a UART may reset the board and center the servos. The app waits for startup, performs a versioned handshake, and stays paused until you calibrate and press Space. The earlier manual-only firmware must be updated before this app can connect.

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

GPIO9 defaults to open=90, closed=0. Set `claw_closed` to the tested closed position (including 180 if that matches your linkage) and keep it inside GPIO9's limits. Pinch closure is proportional to thumb/index separation divided by palm width; `pinch_closed_ratio` sets the fully pinched threshold. The open reference is learned during calibration. Do not reverse both the claw endpoint and its direction unless you intend that combined effect.

The firmware also enforces hard 0..180 bounds and a 90 degrees/second slew limit for manual and tracking moves. `max_speed` in the app may reduce that limit. Narrower app joint limits apply to tracking; manual serial commands use firmware limits. Physical travel may differ from nominal degrees.

## Loss of tracking, pause, and reconnect

A missing control immediately freezes its target. If any control remains missing for 500ms, if camera frames stop, or if a serial command fails, movement pauses. The firmware independently freezes its current output after 500ms without a valid tracking update. It keeps sending holding pulses, rather than dropping the arm or moving it back to center.

Reacquiring your hands does not resume movement: press Space. On USB failure press **R** to reconnect, then **C** and Space. Reconnecting may reboot/recenter the board. Pausing retains calibration and synchronizes the app with the firmware's held output before resuming.

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

If the camera cannot open, press **V** in the window, check Windows **Privacy & security > Camera**, allow desktop apps, or close competing camera apps. The shortcut remains available even when the current camera has no feed. If your only camera failed to open, fix its permissions or competing app, then restart this app to retry it. Camo/virtual cameras may be different indices from the integrated webcam. Models run on the CPU; reduce resolution if the frame-age indicator approaches 500ms. The app retains only the latest captured frame to avoid a growing camera queue. Normal MediaPipe native-library warnings may appear on stderr.

`requirements.txt` lists direct dependencies; `requirements-lock.txt` records the complete tested Python 3.12 Windows environment. Only one OpenCV package is installed. User-specific calibration is kept in memory and must be repeated after restart/reconnect. Editing config requires restarting the app.

## Serial protocol and manual controls

115200 baud, ASCII newline-delimited, protocol version 1. All four pose angles are integers in **GPIO6, GPIO7, GPIO8, GPIO9** order. A whole pose is rejected if any field is invalid. Only one command is in flight at once.

| Command | Response / effect |
|---|---|
| `hello` | `ROBOT_ARM 1 a6 a7 a8 a9`; freezes and pauses |
| `resume` | `OK resume`; allows tracking updates |
| `pose 90 100 80 50` | `OK pose`; sets all four targets |
| `hold` | `OK hold a6 a7 a8 a9`; freezes current outputs |
| Invalid/expired command | `ERR reason`; timeout requires explicit resume |

The tracking sketch includes **absolute-angle** manual commands: `1 90`, `2 45`, `3 120`, `4 60`, `all 90`, `1 off`, `off`, and `help`. Thus `1 90` means center; it does not add 90 degrees. Your preserved `RELATIVE-CW-v4` sample instead uses signed relative increments and `center`/`status`. These are separate firmware programs. Tracking-sketch manual commands pause tracking; manual moves slew to their target without requiring repeated heartbeats. Use them only with the app disconnected. After `off`, `resume` alone leaves pulses disabled; an accepted pose enables the outputs again.

See [verification notes](docs/verification.md) for actual tests and remaining hardware checks.

## Sources

- [MediaPipe Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python)
- [MediaPipe Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python)
- [Espressif Arduino LEDC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
- [ESP32-C5 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf)
- [Waveshare board documentation](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX)
