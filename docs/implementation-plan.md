# MediaPipe robot arm implementation plan

Approved design: local Python 3.12 camera tracking -> USB UART at 115200 -> ESP32-C5 LEDC on GPIO6/7/8/9. Right arm controls elbow/wrist/claw; left hand's clockwise image-plane rotation controls GPIO6. All servos boot at nominal 90 degrees, with the claw open.

## Work and ownership

- [x] Tracking core: pure geometry, calibration, mapping, smoothing, dropout state machine; synthetic landmark and timing tests first.
- [x] Firmware: adapt existing PWM implementation into separate tracking sketch; native C++ behavioral tests first, then ESP32-C5 compile.
- [x] Serial: versioned handshake, checked responses, bounded reads/writes, timeout and reconnect behavior; byte-stream tests first.
- [x] Integration: camera/MediaPipe adapter, OpenCV UI, strict TOML config, model download, Windows setup/run scripts, documentation and runtime smoke checks.
- [x] Review integrated behavior, fix findings, run complete tests and compile; task files ready for the authorized local commit. No push or board flash.

## Serial contract v1

ASCII newline-delimited; angles are integers in GPIO6/7/8/9 order. CRLF also accepted. Maximum received line 95 bytes; invalid lines change no targets. Commands are lowercase.

* `hello` freezes outputs and pauses control; reply `ROBOT_ARM 1 a6 a7 a8 a9` containing rounded current output angles. Boot emits the same identification. Host explicitly sends hello after settling and never treats the boot line as its handshake response.
* `resume` enables tracking at held outputs; reply `OK resume`.
* `pose a6 a7 a8 a9` validates all four 0..180 integers before updating targets, only while resumed; reply `OK pose`. Each accepted pose refreshes the watchdog.
* `hold` freezes current outputs and pauses; reply `OK hold a6 a7 a8 a9`.
* `ERR <reason>` on error. At 500ms without a pose while resumed, freeze outputs, pause and emit `ERR timeout`; subsequent poses rejected until explicit resume.
* Firmware output updates at 50Hz, max 90 degrees/second. Initial outputs 90, 1000..2000us at 50Hz/14bit. Manual `1 90`, `all 90`, `1 off`, `off`, `help` remain, and pause tracking. Manual moves slew to their targets without the tracking watchdog. `off` disables pulses only.

## Python contracts

`arm_control.config`: frozen `JointConfig(minimum=0, maximum=180, direction=1, gain=1)`; `Config(joints: tuple[JointConfig,...]` four in GPIO order, `claw_open=90, claw_closed=0, pinch_closed_ratio=0.2, smoothing_tau=0.12, deadband=1.0, max_speed=90.0, loss_timeout=0.5, calibration_seconds=1.0, confidence=0.6, camera=0, width=960, height=720, send_hz=30.0)`. `load_config(path: Path|None)->Config` validates all input; `Config()` is valid.

`arm_control.control`: `Observation(rotation:float|None, elbow:float|None, wrist:float|None, pinch:float|None)` uses clockwise degrees in mirrored display for rotation and wrist, elbow flexion in degrees (straight=0), pinch distance/palm width ratio. `Controller(config)` exposes `angles` (four floats), `calibrated` bool, `active` bool, `status` str. Methods `begin_calibration(now)`, `update(observation, now)->tuple[float,...]`, `resume(now)->bool`, `pause(reason='Paused')`, `reset(angles=(90,90,90,90))`. Calibration requires all valid values stable for a second, straight elbow/wrist (within 20 degrees), open pinch >0.4; captures neutral including open pinch. Failed tracking freezes affected values immediately, any continuous loss >=0.5s pauses all; resume needs current valid observations. Reacquisition does not auto-resume. Calibration while active pauses. No accumulating angular drift; handle wraparound using shortest relative angle. Rate limit even after long frame gaps; time >=0.5s pauses before applying new movement.

`arm_control.geometry`: `Point(x,y,z=0)`, `angle(a,b,c)` unsigned interior angle degrees with degenerate geometry returning None; `clockwise_angle(vector_x,vector_y)` atan2 direction degrees in screen coordinates; `signed_bend(forearm_x,forearm_y,hand_x,hand_y)` clockwise signed bend; `pinch_ratio(thumb,index,palm_index,palm_pinky)`; `associate_hands(pose_wrists:dict[str,Point], hand_wrists:list[Point], max_distance:float, ambiguity_margin:float)->dict[str,int]` unique assignments, omit ambiguous/out-of-range matches. Coordinates for association are pixel-space scaled by image diagonal.

`arm_control.transport`: `SerialLink(port, timeout=0.5)` owns pySerial; `connect()->tuple[float,...]` blocking handshake, `resume()`, `hold()->tuple[float,...]`, `send_pose(angles)->None` synchronous bounded transaction including exact ACK (one in flight; <=0.5sec), `close()` best effort hold and close; failures raise `LinkError`. `list_ports()->list[tuple[str,str]]`. No automatic reconnect or movement on connect. Constructor can accept serial factory/clock for byte-stream tests if useful; normal pySerial import lazy. Root calls only these public contracts. A failed control transaction disconnects the host and resets calibration; reconnect requires R and full handshake.

## Integration decisions

The user supplied a newer nested `ESP32C5_FourServos/ESP32C5_FourServos/ESP32C5_FourServos.ino` (RELATIVE-CW-v4) during implementation. Preserve that sample byte-for-byte and keep new firmware at `ESP32C5_Tracking/ESP32C5_Tracking.ino`, with its tested `Controller.h` beside it. The new sketch's manual commands are absolute, as in the approved design; the preserved sample's numeric commands are relative. Build scripts and README identify the tracking target explicitly.

USB reconnect waits two seconds for any boot and the tracking watchdog, then sends a NUL followed by a newline to invalidate and discard any old partial command, drains old replies with a bounded timeout, and sends a fresh hello. A bare newline is insufficient: it could execute an unfinished manual command, which is not governed by the tracking watchdog.

Session camera methods use actual capture timestamps, independently of GUI missing-frame polling. A recovered frame after a gap of 500ms must leave control paused until explicit resume. Pausing synchronizes with firmware's reported held positions via Controller.sync_angles without invalidating calibration.

## Acceptance

Tests cover measured geometry, neutral-relative mapping, pinch, reversed/limited joints, drift, smoothing and rate limits, dropout, calibration stability, malformed protocol and stale ACKs. Firmware native tests exercise real production parser/controller. Compile using installed Arduino core 3.3.10 and esp32:esp32:esp32c5 with CDC disabled. Test actual MediaPipe models and integrated camera in dry-run without touching serial hardware. Report physical tracking quality/servo tests separately from automated verification.
