# Verification — 19 September 2026

## Environment and artifacts

- Windows x64, Python 3.12 in project `.venv`.
- MediaPipe 0.10.18, OpenCV contrib 4.10.0.84, NumPy 1.26.4, pySerial 3.5. Complete installed versions are in `requirements-lock.txt`; `pip check` passes.
- Official Hand Landmarker full and Pose Landmarker lite float16/version 1 models downloaded and SHA-256 verified. Model URLs and digests live in `arm_control/models.py`.
- Arduino ESP32 core 3.3.10, FQBN `esp32:esp32:esp32c5:CDCOnBoot=default`.
- Canonical tracking firmware: `ESP32C5_Tracking/ESP32C5_Tracking.ino` and its adjacent production `Controller.h`.

## Automated checks

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test.ps1` passes **83 Python behavior tests** plus the native C++ firmware suite. Coverage includes geometry, anatomical hand association, calibration, absolute neutral-relative mapping, wraparound, limits, smoothing, dropout, capture timestamps, serial framing/reconnect, configuration, camera lifecycle and CLI defaults.

Firmware native tests compile the same `Controller.h` used by the sketch with `-std=c++11 -Wall -Wextra -Werror -pedantic`. They exercise complete/partial/malformed commands, atomic rejection, watchdog pauses, manual/off behavior, rate limits and millis rollover.

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-firmware.ps1` successfully compiles the tracking sketch. Flash usage: **323,484 bytes (24%)**. Static RAM: **17,820 bytes (5%)**. This is a build, not a board upload.

Independent review identified and resolved: the changed location of the user's sample versus the tracking sketch; reconnect after incomplete device-side lines; prevention of completing a buffered manual command during reconnect; and a camera-stall polling gap that could postpone the intended 500ms pause. Regression tests exercise the recovery paths. Final scoped reviews found no remaining issues; the framing reset was also exercised against the actual production C++ parser with pending manual, resume, complete-pose and partial-pose commands.

## Actual runtime checks

- Re-ran the Windows setup script successfully; locked packages resolve and cached models verify.
- Loaded both actual MediaPipe models and processed an empty image; all four control observations correctly report missing.
- Real camera, no serial opened: `python -m arm_control --dry-run --headless --frames 60` completed in **4.75 seconds**, with **24.23ms mean / 31.00ms median inference**. These timings include two landmark models; total elapsed time also includes camera/model startup.
- Real OpenCV window and camera: `python -m arm_control --dry-run --frames 15` exited successfully after **3.01 seconds**, with **28.07ms mean inference**. Reviewed the status panel using a synthetic image; controls and telemetry fit without clipping.
- No full operator control pose was present during camera checks: **0 fully tracked control frames**. Synthetic landmarks verify mapping mathematically; operator gesture quality is not established by these smoke tests.
- Read-only port enumeration found **COM70 — USB-Enhanced-SERIAL CH343**. No serial port was opened, no firmware was uploaded, and no servos were driven during implementation.

## Preserved sample and remaining physical checks

The user supplied a newer `RELATIVE-CW-v4` sketch while work was in progress. It is preserved at `ESP32C5_FourServos/ESP32C5_FourServos/ESP32C5_FourServos.ino`, byte-for-byte SHA-256:

`8a18f64f7c283b8d349a4cc3245250b16ed1b0758a93e90247d5b7151eca66ce`

That relative-command sample is separate from the new absolute-angle tracking firmware. The tracking firmware must be uploaded before the Python app can communicate with it. The original sample remains outside the task's local Git commit.

Physical checks still needed: confirm 90-degree horn alignment/open claw, servo polarity and mechanical endpoints, supply capacity and shared ground; upload tracking firmware; calibrate with the actual operator; test individual movements and tracking/USB-loss holds. Nominal software angles are not measured shaft positions. No claim of physical motion or electrical verification is made.

## Follow-up: board upload and keyboard camera switching

The preceding sections record the initial implementation checks. Subsequently, at the user's request:

- Identified the connected board as ESP32-C5 revision 1.0 on COM70, uploaded the tracking firmware successfully, and verified flash hashes. The running firmware returned `ROBOT_ARM 1 90 90 90 90`; a hold command also reported all four nominal angles at 90.
- Added **V** camera switching, with no on-screen button. Switching holds the arm, clears calibration, probes alternate cameras without blocking the preview loop, and rebuilds the landmark trackers. Unavailable alternatives retain the previous camera. An unavailable startup camera can be bypassed with V.
- Passed **99 Python tests** and the native production firmware controller tests. An independent code review found no blocking issues.
- Restarted the full app with `--port COM70`. Verified a native V key event changed the real preview from camera 0 to camera 1 while remaining connected and paused at 90 degrees on all four outputs.
- Camera 1 displayed live video with both hand overlays and arm landmarks. The observed frame supplied all four control values, with 47 ms inference and 63 ms frame age. This is a single observed frame, not a performance benchmark. The app remains open for operator calibration and control.

The camera change is local to the Python app; no additional firmware upload was needed. Mechanical alignment, endpoint suitability, and actual gesture-to-servo motion still require operator validation. Camera screenshots and runtime logs remain in ignored local `artifacts/` and are not committed.

## Follow-up: calibration feedback and hand sensitivity

- Added distinct calibration messages for missing controls, excessive elbow/wrist bend, and insufficient thumb/index separation. Capture progress and the specific stability-reset cause are now visible. The four-second countdown and explicit Space-to-start behavior are retained.
- Fixed hand filtering that treated left/right classification confidence as detection confidence, even though ownership is determined from pose wrists. Slightly clipped fingertips are accepted within a 5% image margin; the wrist must stay inside the image and all landmarks must remain finite.
- Split hand model thresholds from pose confidence: hand detection/presence/tracking now use configurable `hand_confidence = 0.35`; pose confidence remains 0.6. These more permissive settings need operator assessment for detection quality and false positives.
- All **105 Python tests** pass, including regression cases for clipped fingertips, uncertain handedness, rejected outliers, calibration guidance, countdown and calibration progress. Restarted the actual models and GUI on camera 1 with the COM70 connection confirmed.
- Successful operator calibration under the new settings has not yet been observed. The changes expose remaining pose/tracking blockers rather than silently relaxing the neutral-pose requirements.
