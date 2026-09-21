# Control the arm with just your keyboard

This version gives the robot arm its own control window, with no camera or hand tracking. Use the number keys to position each joint, pause and resume, and save your current pose as zero. It works with the same ESP32 firmware and wiring as the tracking version.

[Back to the README](../README.md)

## Already using the robot arm?

Double-click **[Start Robot Arm Keyboard.cmd](../Start%20Robot%20Arm%20Keyboard.cmd)**. It connects to **COM70** and starts paused. Close the original controller first so the USB port is available.

Click the keyboard controller window, then use the keys below. The original camera controller and its launcher remain available separately.

The showcase console includes a dimensional arm schematic, color-matched joint dials, and eight seconds of command history. The illustration responds to your commands; it is not a measured pose or a mechanical simulation. Setting zero keeps the illustration and history anchored to the same raw commands. Smaller windows simplify the layout, with scrolling available when needed.

The schematic uses a short IO6–IO7 base link and an extended IO8–IO9 tool link. IO7's visual direction is reversed to match the motor mounting and moves at half scale: a 7° command changes the illustration by 3.5°. Raw 90 remains upright, and the full sweep remains available with larger commands. This changes the illustration, not the motor's key mapping or travel limits.

Press **F11** for fullscreen presentation mode and press it again to return to the window. The joint key buttons also work with the mouse. **Tab** moves between buttons and **Enter** activates the focused button.

If your board has a different port, edit `ROBOT_ARM_PORT=COM70` in the new launcher. You can also supply a port from PowerShell:

```powershell
& '.\Start Robot Arm Keyboard.cmd' COM9
```

## First-time setup

Install Python 3.12 for Windows with its Python launcher and Tcl/Tk support (included in the standard installer), then download this repository. From the repository folder, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-keyboard.ps1
```

This creates or reuses `.venv` and installs **pyserial 3.5**. The window uses Python's built-in Tkinter. This setup does not install MediaPipe, OpenCV, or tracking models. Existing tracking dependencies in a reused environment can stay installed; the keyboard controller does not use them.

Try the interface without connecting to hardware:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1
```

This is a dry run: the displayed angles change, but no serial connection opens and no motor commands are sent.

For a new arm, follow the [wiring and firmware instructions](setup.md#4-wire-the-servos). Use the `ESP32C5_Tracking` sketch; its name is shared with the original app, but it also supports the keyboard controller. No firmware update is needed when switching between the two apps if the current protocol 2 firmware is already installed.

Find the board's port, then connect using that port:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1 -ListPorts
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1 -Port COM9
```

Replace `COM9` with your board's port. After setup, use the double-click launcher for future sessions.

## Controls

Keep the controller window focused while using the keyboard. Turn **Num Lock on** for the numpad; the number row works too.

| Joint | Decrease | Increase |
|---|---|---|
| GPIO6 | Numpad **1** | Numpad **2** |
| GPIO7 | Numpad **4** | Numpad **5** |
| GPIO8 | Numpad **7** | Numpad **8** |
| GPIO9 / claw | Numpad **3** | Numpad **6** |

Each press changes the target by **7 degrees**. Holding a key repeats at **1.5 times the Windows keyboard repeat rate**, beginning after one repeat interval instead of the usual initial typing delay. Keyboard movement is immediate; there is no tracking smoothing.

| Key | Action |
|---|---|
| **Space** | Resume or pause; the window shows the current state. |
| **C** | Start a four-second countdown, then set the current commanded pose as zero. |
| **R** | Reconnect to the ESP32. |
| **F11** | Toggle fullscreen for a showcase or demonstration. |
| **Q** or **Esc** | Quit. |

A joint key automatically resumes control, including when paused. During zeroing, a joint key cancels the countdown and moves that joint.

## Set a comfortable starting pose

1. Position the arm with the joint keys.
2. Press **C** and wait four seconds.
3. The current commanded position of every joint becomes **0 degrees** in the controller.

The servos stay powered and keep their position throughout. Saving zero does not move the arm, and it preserves whether control was running or paused. No camera, body pose, or hand detection is involved.

Zero is a reference for the current app session. It is not a physical position measurement: these servos do not report their shaft positions, so reposition with the keys rather than by moving the arm by hand. Restarting the app clears the saved reference.

## Useful things to know

- The controller starts paused. Pausing holds the arm's current commanded position; it does not cut servo power.
- Angles can go below zero and beyond plus or minus 90 degrees. The app does not add joint limits or automatic pauses. Physical servo travel and the firmware's electrical output range still apply.
- The ESP32 centers the servos when it boots. Power the servos from the external supply with a common ground, as described in the [wiring guide](setup.md#4-wire-the-servos).
- Run one controller at a time. If the USB port is busy, close the other app or Arduino Serial Monitor and press **R** to reconnect.
- If the launcher reports missing Python or dependencies, rerun `scripts\setup-keyboard.ps1`. If Tkinter is missing, modify your Python installation to include Tcl/Tk support.

For terminal use, the underlying command is `python -m arm_control.keyboard_only` from the project's virtual environment. Add `--dry-run`, `--port COM9`, or `--list-ports` as needed. See the [technical reference](reference.md) for the shared serial protocol and firmware.
