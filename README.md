# Robot Arm, Meet Your Hands 👋

Control a small four-servo robot arm with your own arm and hand movements—or take over with the number keys.

A webcam watches your movements, MediaPipe tracks them on your laptop, and an ESP32-C5 drives the servos over USB. Once the dependencies and models are downloaded, tracking runs locally without Wi-Fi or a cloud service. The app does not record video.

**[Start here: setup guide →](docs/setup.md)** · [Controls](#take-control) · [Settings and protocol](docs/reference.md)

## What it does

| Your movement | Robot control | Servo pin |
|---|---|---|
| Turn your left hand like a clock hand | Base/rotation joint | GPIO6 |
| Bend your right elbow | Arm joint | GPIO7 |
| Bend your right wrist | Wrist joint | GPIO8 |
| Pinch or open your right thumb and index finger | Claw | GPIO9 |

- **Set your own starting pose.** Position the robot with the keys, press **C**, and get comfortable during the four-second countdown. The servos stay powered; their current positions become zero without recentering.
- **Smooth tracking.** All four tracked movements ease toward their targets with a two-second smoothing time constant.
- **Switch cameras with V.** Use a webcam or a virtual camera such as Camo.
- **Take over with the keyboard.** Manual control works without hand detection or calibration.

The tested setup is **Windows x64, Python 3.12, a Waveshare ESP32-C5-WIFI6-KIT-N16R4, and four positional servos**. The supplied configuration was tuned on that arm; adjust it for your own mechanism.

## Try the camera preview

You can try tracking before connecting any hardware. Install [Git](https://git-scm.com/downloads) and [Python 3.12 for Windows](https://www.python.org/downloads/windows/), then open PowerShell:

```powershell
git clone https://github.com/HaiderAli3D/robot-arm-small.git
cd robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Camera 0
```

Setup creates a virtual environment, installs the pinned dependencies, and downloads the official MediaPipe models with checksum verification. The preview command **does not connect to or move the robot**.

Keep your right shoulder, elbow, wrist, and both hands in view. Press **V** if you need another camera. Camera numbers vary between computers; the saved configuration defaults to camera 1, while the example above explicitly selects camera 0.

Ready to move the robot? Follow the **[wiring, firmware, and first-movement walkthrough](docs/setup.md)**. Use the tracking sketch in `ESP32C5_Tracking`, then launch with your board's port, for example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Port COM9 -Camera 0
```

Replace `COM9` with your ESP32's actual USB UART port. The app starts paused.

**For future launches:** after setup, double-click [`Start Robot Arm.cmd`](Start%20Robot%20Arm.cmd). It uses COM70 and your saved camera settings; see the [setup guide](docs/setup.md#start-with-a-double-click-next-time) to change the port.

## Take control

Click the camera window so it receives your key presses.

| Key | Action |
|---|---|
| **Space** | Start or pause |
| **C** | Set a new reference after four seconds; keep the current robot pose |
| **M** | Return from keyboard control to tracking |
| **V** | Switch camera |
| **R** | Reconnect USB |
| **Q / Escape** | Quit |

For manual movement, turn **Num Lock on**:

| Joint | Decrease | Increase |
|---|---|---|
| IO6 rotation | Numpad **1** | Numpad **2** |
| IO7 elbow | Numpad **4** | Numpad **5** |
| IO8 wrist | Numpad **7** | Numpad **8** |
| IO9 claw | Numpad **3** | Numpad **6** |

Each press changes the target by **7 nominal degrees**. Holding a key repeats at **1.5× the Windows keyboard repeat rate**, without the usual initial hold delay. Number-row digits also work. A servo key immediately selects keyboard control and resumes movement, even if you were paused.

### Your first calibration

1. Use the keys to put the robot in a comfortable starting position.
2. Press **C**, then show both hands and your right arm during the four-second countdown. Any visible pose is fine—no need to straighten your arm or fully open your fingers.
3. Wait for **“Current positions zeroed”**. If a landmark is missing, the window tells you what to bring into view.
4. Check the banner: **RUNNING** means movements are active; press **Space** only if it says **PAUSED** and you want to start.

Calibration preserves your running/paused choice. It uses the positions commanded by the app; these servos cannot report a position you set by moving them by hand. References are kept for the current session and cleared when the app restarts.

## Make it feel right

Edit [`config.toml`](config.toml) and restart the app to apply changes.

| Setting | Supplied value | What it changes |
|---|---|---|
| Joint `gain` for IO6 / IO7 / IO8 | `4` | Response to left-hand rotation, elbow bend, and wrist bend |
| Joint `gain` for IO9 | `5` | Pinch sensitivity |
| `smoothing_tau` | `2.0` | Tracking smoothness; two-second time constant |
| `hand_confidence` / `confidence` | `0.2` / `0.4` | Hand and pose detection thresholds |
| Joint `direction` | `1` | Set to `-1` to reverse that joint's gesture response |

Smoothing starts immediately: a steady target change reaches about 63% after two seconds and 95% after six. Keyboard steps remain immediate. See the [reference](docs/reference.md) for how angles, gains, and pinch are mapped.

> **Before powering the arm:** use a suitable external servo supply with a common ground. Booting the board can center the servos. This controller does **not** impose joint travel limits or automatically pause when tracking disappears; missing controls keep their last target. Read the [hardware setup notes](docs/setup.md) before live control.

## Around the project

| Path | What's inside |
|---|---|
| [`arm_control/`](arm_control/) | Camera, MediaPipe tracking, keyboard input, and USB control |
| [`ESP32C5_Tracking/`](ESP32C5_Tracking/) | Firmware used by the app |
| [`ESP32C5_FourServos/`](ESP32C5_FourServos/) | Original standalone serial-control example; a different protocol |
| [`scripts/`](scripts/) | Setup, launch, build, and test helpers |
| [`tests/`](tests/) | Python tests and native firmware controller tests |
| [Setup guide](docs/setup.md) | Installation, wiring, firmware upload, and troubleshooting |
| [Technical reference](docs/reference.md) | Configuration, protocol, and developer commands |
| [Verification notes](docs/verification.md) | Development history and recorded checks |

Found something odd? [Open an issue](https://github.com/HaiderAli3D/robot-arm-small/issues) with your board, camera, Python version, and the error or behavior you saw. Please leave personal camera footage and credentials out of reports.
