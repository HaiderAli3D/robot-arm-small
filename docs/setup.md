# Set up your robot arm

Let's get the camera working first, then connect the arm. You can try all the tracking and keyboard controls in preview mode before plugging in an ESP32.

This guide covers the tested setup: **64-bit Windows, Python 3.12, an ESP32-C5, and four positional servos**. The laptop processes the camera video locally; USB carries the servo commands to the board. Internet access is needed for the initial software and model downloads, but not for normal tracking.

[Back to the README](../README.md)

## 1. Gather the parts and tools

You will need:

- A Windows laptop with a webcam, or a working Camo camera feed.
- An ESP32-C5 board. This project was tested with the **Waveshare ESP32-C5-WIFI6-KIT-N16R4**.
- A USB **data** cable for the board's **UART** USB-C connector.
- Four positional servos, such as MG90S, and your arm mechanism. Continuous-rotation servos will not work as position-controlled joints.
- A regulated 5V servo supply sized for the combined load, plus wiring for the signals and a common ground.

Install these tools:

| Tool | What to install |
|---|---|
| [Git for Windows](https://git-scm.com/install/windows) | Used to download and update this repository. |
| [Python 3.12 for Windows](https://www.python.org/downloads/release/python-31210/) | Choose the **Windows installer (64-bit)** and include the Python launcher. The setup script uses `py -3.12`; the linked release provides a standard Windows installer. |
| [Arduino IDE](https://www.arduino.cc/en/software/) | Needed to upload the ESP32 firmware. You can leave this until after the camera preview works. |

Open a new PowerShell window after installation and check:

```powershell
git --version
py -3.12 --version
```

The Python command should report `Python 3.12.x`. The project's dependency lock file targets this version on Windows.

## 2. Download and install the app

In PowerShell, go to the folder where you keep projects, then run:

```powershell
git clone https://github.com/HaiderAli3D/robot-arm-small.git
cd robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Setup creates a local `.venv`, installs the pinned dependencies, and downloads the official MediaPipe hand and pose models. It checks their SHA-256 hashes before accepting them. You do not need to activate the virtual environment manually.

Keep subsequent commands in this repository folder. The `-ExecutionPolicy Bypass` option applies to that PowerShell invocation; it does not permanently change your Windows execution policy.

## 3. Try the camera preview

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Without `-Port`, the app runs in **preview mode** and never opens a serial connection. The values on screen let you try the controls without moving hardware.

The supplied configuration starts with camera **1**. Camera numbers depend on your laptop: press **V** in the preview window to cycle through available cameras at indices 0–3. To start with camera 0 instead:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Camera 0
```

Keep your right shoulder, elbow and wrist, plus both hands, in view. Use one person in the frame, keep the hands apart, and face your right palm toward the camera so the thumb and index finger are visible.

Press **C**, then use the four-second countdown to get into a comfortable pose. Any detected pose is accepted: your arm does not need to be straight, and your fingers do not need to be open. After the countdown, calibration waits for all four controls to be visible and saves that pose as the reference.

If the banner says **PAUSED**, press **Space** to begin tracking. If it already says **RUNNING**, you are ready. Press **Q** or **Escape** to close the preview before continuing.

## 4. Wire the servos

Make the wiring connections with the servo supply disconnected.

| ESP32 signal pin | Joint control | Servo signal wire |
|---|---|---|
| GPIO6 / IO6 | Left-hand rotation in the camera image | Rotation servo |
| GPIO7 / IO7 | Right elbow bend | Elbow servo |
| GPIO8 / IO8 | Right wrist bend relative to the forearm | Wrist servo |
| GPIO9 / IO9 | Right thumb/index pinch | Claw servo |

Connect all four servo power wires to the external regulated **5V** supply. Connect the servo grounds, supply ground, and an ESP32 **GND** pin together. Power the ESP32 through its USB connection.

**Keep the external servo +5V rail separate from the board/laptop USB +5V rail.** GPIO pins carry only the servo signals; they do not supply servo power. Check your servo's wire labels or datasheet rather than relying on wire colors.

At boot, the firmware commands all four channels to their nominal center: raw position **90**, corresponding to a 1500µs pulse. The mechanism is assumed to be mounted with the arm straight and the claw open at this position. If assembling from scratch, establish those servo centers before fastening the horns/linkages in their neutral positions. Uploading, rebooting, or opening the USB serial connection can center the arm again.

GPIO7 is also an ESP32-C5 reset-time strapping pin; avoid adding circuitry that forces its reset level. For board-specific connector and pin details, see the [Waveshare documentation](https://www.waveshare.com/wiki/ESP32-C5-WIFI6-KIT-NXRX).

## 5. Upload the tracking firmware

In Arduino IDE:

1. Open **File → Preferences** and add this URL to **Additional Boards Manager URLs**:

   ```text
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```

2. Open **Boards Manager**, search for **esp32**, and install **esp32 by Espressif Systems**, version **3.3.10**, the version tested for this project. These package installation steps follow [Espressif's official guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html).
3. Open [`ESP32C5_Tracking/ESP32C5_Tracking.ino`](../ESP32C5_Tracking/ESP32C5_Tracking.ino). The separate `ESP32C5_FourServos` folder is a standalone sample and does not speak the app's tracking protocol.
4. Select **ESP32C5 Dev Module** and set **USB CDC On Boot → Disabled**.
5. Connect the board's **UART** USB connector, select its COM port, and upload. Leave room for the arm to center if the servos are powered.
6. Close **Serial Monitor** before starting the app, so the app can open the port.

The app requires the current **protocol 2** tracking sketch. Uploading an older protocol 1 build or the standalone sample will not work with this app.

## 6. Connect the app to the arm

Find the serial port:

```powershell
.\.venv\Scripts\python.exe -m arm_control --list-ports
```

Choose the board's USB UART port, then start live control. Replace `COM9` with your port:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 -Port COM9
```

You can also add `-Camera 0` if needed. The connection status should say **Connected** and name the port. A fresh app session starts **PAUSED**; this holds the commanded position with the servos powered.

### Start with a double-click next time

After setup and firmware upload, double-click [`Start Robot Arm.cmd`](../Start%20Robot%20Arm.cmd) in the project folder. It starts live control using **COM70** and the camera selected in `config.toml`. The app still starts paused; click its camera window to use the controls.

If your board uses another port, right-click the launcher, choose **Edit** (or open it in Notepad), and change `set "ROBOT_ARM_PORT=COM70"` to your port. You can also pass a port from PowerShell: `& '.\Start Robot Arm.cmd' COM9`. The launcher works regardless of the current folder and keeps its console open if startup fails so you can read the error.

### Position the arm, then make that position zero

1. Click the preview window and turn **Num Lock on**.
2. Tap the servo keys below to position the arm. **A servo key starts keyboard control and resumes movement immediately**, even from paused mode.
3. Release the keys and press **C**. The servos stay powered and hold their current commands during the four-second countdown.
4. Show both hands and your right arm. When calibration completes, each current servo command becomes its displayed **0°**, and your detected pose becomes the gesture reference. Calibration does not change the servo targets or send the arm back to center.
5. Check the banner. Calibration preserves the existing run/pause choice: press **Space only if PAUSED** and you want to start. If already **RUNNING**, move from your reference pose to control the arm.

These servos have no shaft-position feedback. Use the keys to choose the pose; the app cannot discover a new physical position created by moving an unpowered arm by hand. Its displayed angles are commands, not measurements.

## Everyday controls

| Key | Action |
|---|---|
| Numpad **1 / 2** | Decrease / increase IO6 |
| Numpad **4 / 5** | Decrease / increase IO7 |
| Numpad **7 / 8** | Decrease / increase IO8 |
| Numpad **3 / 6** | Decrease / increase IO9 |
| **C** | Select tracking and calibrate after four seconds |
| **M** | Return from keyboard control to tracking |
| **Space** | Toggle running / paused |
| **V** | Switch camera |
| **R** | Reconnect USB |
| **Q / Escape** | Quit |

Each servo key press requests a **7°** step. On Windows, holding it repeats at **1.5× the Windows keyboard repeat rate**, with the first repeat due after one interval and no extra hold delay. Updates follow the app's frame timing; this does not change a motor's physical maximum speed. Matching number-row digits also work. Release and press again after Space, C, M, or leaving the window to begin a new hold.

Keyboard positions remain in place until you change them; gestures cannot overwrite them in keyboard mode. **M** and **C** retain your running/paused choice. Calibration zeros and references last for the app session, including camera switches and reconnects, but are cleared when you restart the app.

**RUNNING** means the app intends to keep controlling the arm. Missing hands, a camera interruption, or a USB failure do not automatically select pause. A missing tracked control holds its last target while visible controls continue. Returning tracking or reconnecting can resume updates. **PAUSED** holds the current output; it does not remove servo power.

## Adjust the feel

Edit [`config.toml`](../config.toml), then restart the app to apply changes.

| Setting | Supplied value | Effect |
|---|---|---|
| `camera` | `1` | Startup camera index |
| `width`, `height` | `960`, `720` | Maximum processing dimensions; aspect ratio is preserved |
| `confidence` | `0.4` | Pose detection/tracking threshold |
| `hand_confidence` | `0.2` | Hand detection, presence and tracking threshold |
| `smoothing_tau` | `2.0` | Tracking smoothing time constant in seconds |
| Joint `gain` for IO6, IO7, IO8 | `4` | Gesture angle sensitivity |
| Joint `gain` for IO9 | `5` | Pinch sensitivity |
| Joint `direction` | `1` | Use `-1` to reverse that tracking control |

The two-second smoothing starts moving immediately and reaches about **63%** of a sustained target change after two seconds, or **95%** after six. Keyboard steps bypass tracking smoothing, gain, and direction.

Pinch uses thumb/index separation relative to palm width. Its gain multiplies the change from your calibrated pinch, so calibrating while partly pinched is fine. If a small pinch moves the claw too far, reduce `gain` in `[joints.gpio9]` and recalibrate from a useful commanded position.

There are **no configured joint travel limits**. A large gain or a long key hold can request positions far beyond a servo's actual travel, including beyond the useful pulse range. Larger displayed numbers do not mean the mechanism can reach them. Choose gains and commands for your particular linkage.

## If something isn't working

| Symptom | What to try |
|---|---|
| `py -3.12` is not found | Install 64-bit Python 3.12 with its launcher, open a new PowerShell window, then rerun setup. |
| Dependencies or models fail to download | Check the connection and rerun `setup.ps1`. It is fine to rerun setup in the same folder. |
| Black preview or the wrong camera | Press **V**. Check Windows camera privacy settings and access for desktop apps. Close competing camera apps. For Camo, first confirm its own preview works. If the only camera failed to open, fix the cause and restart this app. |
| Hands disappear or calibration keeps waiting | Improve lighting; show both hands and the right shoulder/elbow/wrist; keep hands separated and thumb/index visible. The message below the banner identifies the missing control. Calibration accepts any pose but still needs detected landmarks. |
| No port appears | Check the USB data cable and the board's **UART** connector. Check Device Manager and the board manufacturer's USB UART driver instructions. Bluetooth COM ports are not the arm. |
| Port busy or access denied | Close Arduino Serial Monitor and any other copy of the app. Then restart, or press **R** to reconnect. |
| Handshake or protocol error | Upload the current **ESP32C5_Tracking** sketch with **USB CDC On Boot disabled**. Check that the selected port belongs to this board. |
| Keys do nothing | Click the preview window, turn Num Lock on, and release/repress the key. Try the matching number-row digit. |
| Gestures do nothing after using the keys | Press **M** to select tracking, or **C** to set a new reference. Check the banner and USB connection status. |
| Claw stops moving after a long hold or large pinch | The requested position may be far outside useful travel. Pause, inspect the displayed command, and use brief opposite-direction key taps to bring the command back toward the last useful range. Reduce claw gain if needed. Pressing **C** only renames the current command as zero; it does not correct an out-of-range target. |
| Motion feels delayed | Tracking has two-second smoothing by design. Try keyboard control to distinguish smoothing from camera lag. Lower processing dimensions if inference is slow. |

Close the app, then inspect camera availability without opening a serial port:

```powershell
.\.venv\Scripts\python.exe -m arm_control --list-cameras
```

Neither the app nor firmware knows the actual shaft position or whether a linkage has reached an end stop. If the displayed command no longer matches useful movement, stop adding commands and inspect the mechanism. Power cycling may recenter it; disconnect servo power before changing linkages.

## Updating and checking the installation

Close the app before updating. If you have edited `config.toml`, keep a copy of your settings and resolve any Git conflicts before running setup again.

```powershell
git pull
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

You only need to upload firmware again when the firmware changes or the app requires a newer protocol. Installing Python dependencies does not upload anything to the ESP32.

For a Python test run that does not operate the arm:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

See [verification notes](verification.md) for recorded software and hardware checks.
