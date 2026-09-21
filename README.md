# Robot Arm Control 🤖

Four joints. Eight keys. Your own robotics console.

Drive a small ESP32-C5 robot arm from a desktop control panel built for hands-on demos. Watch the articulated schematic follow your commands, see each joint's position, and press **F11** to put the console on the big screen.

**[Start here: keyboard console guide](docs/keyboard-only.md)** · [Quick start](#try-it-without-a-robot) · [Controls](#take-the-controls) · [Camera tracking](#want-to-control-it-with-your-hands)

![Keyboard console with an articulated arm schematic, four joint controls, command history, and a paused preview status.](docs/images/keyboard-console.jpg)

*The console in preview mode. The arm is an illustration of commanded positions, not sensor feedback.*

## Meet the keyboard console

- **An arm that moves with you.** A dimensional schematic shows rotation, elbow, wrist, and claw movement, with matching colors across the joint controls.
- **A clear view of every command.** Large angle readouts, joint dials, and eight seconds of command history help make a demonstration easy to follow.
- **Ready for the showcase.** Fullscreen mode, clickable controls, and clear Running / Paused status keep attention on the arm.
- **Choose your own zero.** Position the arm, press **C**, and wait four seconds. The servos stay powered and their current positions become zero without snapping back.
- **No camera needed.** The keyboard version runs locally with Python, Tkinter, and pyserial. No MediaPipe, OpenCV, or model downloads are required.

Already set up? Close any other controller, then double-click **[Start Robot Arm Keyboard.cmd](Start%20Robot%20Arm%20Keyboard.cmd)**. It uses COM70 by default; the [guide explains how to change the port](docs/keyboard-only.md).

## Try it without a robot

Install [Git for Windows](https://git-scm.com/install/windows) and [64-bit Python 3.12](https://www.python.org/downloads/release/python-31210/) with its launcher and Tcl/Tk support. Open PowerShell:

```powershell
git clone https://github.com/HaiderAli3D/robot-arm-small.git
cd robot-arm-small
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-keyboard.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1
```

This opens **preview mode**: you can explore the complete console without opening a serial port or moving hardware. Click the window, tap **2**, and watch the rotation joint respond. Press **F11** for fullscreen, then **Q** to quit.

Setup creates or reuses `.venv` and installs pyserial 3.5. You do not need to activate the environment manually.

## Take the controls

Turn **Num Lock on** and keep the controller window focused. Number-row digits work too.

| Joint | Decrease | Increase |
|---|---|---|
| IO6 · Rotation | **1** | **2** |
| IO7 · Elbow | **4** | **5** |
| IO8 · Wrist | **7** | **8** |
| IO9 · Claw | **3** | **6** |

Each press changes the command by **7 nominal degrees**. Hold a key to repeat at **1.5× the Windows keyboard repeat rate**, without the usual initial typing delay. The on-screen joint buttons also move one step per click.

| Key | Action |
|---|---|
| **Space** | Resume / pause |
| **C** | Save the current position as zero after four seconds |
| **F11** | Fullscreen / windowed |
| **R** | Reconnect USB |
| **Q / Esc** | Quit |

**A joint key or joint button resumes movement, even when paused.** Pressing it during the zeroing countdown cancels that countdown. Zeroing otherwise preserves the run/pause state.

The schematic is tuned to this arm's proportions. IO7 is visually reversed and uses half-scale movement: a 7° command moves that part of the drawing by 3.5°. Motor commands and numerical readouts keep their original values.

## Put the real arm on stage

The tested hardware is a **Waveshare ESP32-C5-WIFI6-KIT-N16R4** with four positional servos on **GPIO6, 7, 8, and 9**, connected to a Windows laptop through USB UART.

Follow the [keyboard guide](docs/keyboard-only.md) for the full walkthrough, including the shared [wiring](docs/setup.md#4-wire-the-servos) and [firmware upload](docs/setup.md#5-upload-the-tracking-firmware) steps. Both controllers use the `ESP32C5_Tracking` sketch, despite its name.

Once the firmware is ready, find the board and connect:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1 -ListPorts
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-keyboard.ps1 -Port COM9
```

Replace `COM9` with your board's port. The console starts **Paused**. Position the arm with the keys, use **C** to save your starting pose, and **F11** to show it off.

> Power the servos from a suitable external supply with a common ground. Booting the board can center them. Pause holds position with power on; this controller does not impose mechanical travel limits. See the wiring guide before live use.

## Want to control it with your hands?

The original **MediaPipe camera controller** is still included. Your left hand controls IO6 rotation; your right elbow, wrist, and pinch control IO7, IO8, and IO9. It includes camera switching with **V** and smooth gesture control.

Use the **[camera setup guide](docs/setup.md)** for its separate installation and calibration flow. Its launcher is **[Start Robot Arm.cmd](Start%20Robot%20Arm.cmd)**. Run one controller at a time so they do not compete for the USB port.

| Choose this | When you want… |
|---|---|
| [Keyboard console](docs/keyboard-only.md) | Direct control, no webcam, and the showcase UI |
| [Camera controller](docs/setup.md) | Arm and hand gestures driving the robot |

## Explore the project

- [Keyboard guide](docs/keyboard-only.md): installation, screen tour, first demo, and troubleshooting.
- [Camera and hardware setup](docs/setup.md): gesture tracking, wiring, and firmware upload.
- [Technical reference](docs/reference.md): the shared serial protocol and tracking configuration.
- [Firmware](ESP32C5_Tracking/): the ESP32-C5 controller used by both apps.
- [Tests](tests/) and [verification notes](docs/verification.md): checks and development history.
- [Original four-servo sample](ESP32C5_FourServos/): a standalone example with a different protocol.

Found something odd? [Open an issue](https://github.com/HaiderAli3D/robot-arm-small/issues) with the controller version, board, Python version, and what happened. A short error message or screenshot of the console helps; leave credentials and personal footage out of reports.
