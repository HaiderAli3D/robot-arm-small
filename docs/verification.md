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

## Follow-up: unrestricted pose snapshot

At the user's explicit request, removed the straightness, open-hand and stability requirements described in earlier sections. Calibration now accepts the first complete tracked frame after the four-second countdown. It records three arm/wrist reference angles, stays paused, and imposes no additional sampling delay. The obsolete `calibration_seconds` setting has been removed.

Claw mapping uses independent, validated `pinch_open_ratio` and `pinch_closed_ratio` endpoints. Calibrating while pinched is accepted without a zero/negative denominator; the claw still follows pinch/open directly after Space. All **105 Python tests** pass, including arbitrary bent/pinched poses, immediate capture at the four-second deadline, angular wraparound, missing tracking, no movement on capture, pinched-reference edge cases, and invalid claw endpoint settings.

## Follow-up: manual-only run/pause

At the user's request, removed automatic pauses for tracking loss, camera gaps, old frames, camera switching, calibration, and USB faults. The run selection and reference survive reconnects; R restores hardware tracking if running was selected. Space can toggle mode while a camera is unavailable or switching. Starting without calibration captures the first complete reference automatically. Missing controls retain their last angles while visible controls continue.

Removed the firmware's 500 ms inactivity watchdog, the firmware/app servo slew caps, and the help command's implicit pause. Command framing, finite numeric values, and the supported nominal servo-angle range remain. Explicit Space/hold, quitting, and firmware manual/off commands still work. Removed obsolete `max_speed` and `loss_timeout` settings. A camera recovery bug was also fixed: fresh frames now recover after a long stall rather than being discarded based on the previous frame's age.

The ESP32-C5 firmware compiled using the existing target/core (323,224 bytes flash, 17,804 bytes static RAM), then was uploaded to the identified ESP32-C5 on COM70 with user approval and verified flash hashes. Actual serial test: boot/hold reported all four nominal angles at 90; after resume and a 1.2-second command gap, the board accepted another pose without another resume. This verifies removal of the old timeout on the connected board without requesting movement away from center. The full application was restarted on COM70 and camera 1.

Final verification: **118 Python tests** and native firmware tests pass. GUI regressions cover camera recovery after a >10-second stall and Space/C behavior during failure and probing. The real app was observed connected and **RUNNING** with left-hand tracking missing while right elbow/wrist/pinch observations and commanded outputs continued (observed commanded values: GPIO6 90.0, GPIO7 111.7, GPIO8 87.0, GPIO9 87.6). These are commanded values, not measured shaft angles. The app was left running for the user.

## Follow-up: elbow/wrist pin swap and claw response

Changed the host mapping at the user's request: GPIO7 now follows right wrist bend and GPIO8 follows right elbow bend. GPIO6 rotation and GPIO9 claw remain assigned as before. The UI now labels the pin associated with each input. Increased the supplied GPIO9 gain from 1 to 2: with the configured pinch endpoints, ratios 1.0, 0.8, and 0.6 command claw targets 90, 45, and 0 degrees respectively before smoothing.

All **120 Python tests** pass. Independent elbow-only and wrist-only input tests verify output order; missing-input and per-pin gain/direction tests use the revised mapping. The claw regression loads the actual project configuration and verifies doubled response, full closure, and reopening. Firmware is unchanged; this host-side mapping update requires only restarting the app.

## Follow-up: keyboard servo control

Added W/E for IO6, T/Y for IO7, U/I for IO8, and P/[ for IO9; the first key decreases and the second increases by five nominal degrees. A servo key selects keyboard mode, starts control, and sends immediately. Camera observations cannot change targets in keyboard mode. M returns to tracking, C selects tracking and calibrates, and Space pauses/resumes either mode. Keyboard control works without camera detection/calibration and survives reconnects.

All **134 Python tests** pass, including all eight keys, uppercase input, actual pin order, direct increments independent of tracking gain, immediate serial sends, camera isolation, manual pause/resume, offline/reconnect behavior, and transitions back to tracking. Restarted the full app on COM70 and camera 1. Firmware is unchanged.

## Follow-up: corrected elbow/wrist mapping and signed positions

At the user's corrected request, GPIO7 follows right elbow bend and GPIO8 follows right wrist bend. GPIO6 left-hand rotation and GPIO9 pinch retain their assignments. Removed the pending shoulder-control implementation. Calibration still accepts any complete detected pose after four seconds, and running stays selected until explicit pause. Keyboard pairs remain W/E, T/Y, U/I, and P/[ for GPIO6 through GPIO9.

All four displayed positions and the new Session.set_position API use -90..+90 degrees around center (0). The existing firmware protocol remains 0..180; signed positions translate by adding 90. Physical travel and pulse widths are unchanged. Tests cover signed commands on every pin, invalid inputs, keyboard steps below center, per-joint limits, independent elbow/wrist mapping, and retained calibration/run behavior.

All 140 Python tests pass; independent code review found no actionable defects. Restarted the full application on COM70 and camera 1 and observed the corrected IO7 elbow / IO8 wrist labels, signed outputs, and connected paused status. The preview was black during this check, so live gesture-to-servo movement was not verified. Firmware is unchanged and was not reflashed. Runtime logs and the own-window screenshot remain in ignored artifacts/.

## Follow-up: removal of nominal joint travel caps

Removed the host tracking/keyboard clamps and the minimum/maximum joint configuration fields. Every channel can command positions beyond signed -90/+90. Session.set_position, held-position synchronization, and serial encoding accept extended positions. Protocol 2 uses exact signed 32-bit raw integers, with raw 90 still representing signed center 0; the host explicitly rejects older protocol versions. The original FourServos sample is untouched.

Firmware pose and manual commands accept signed integers without the former raw 0..180 gate. Exact int32 storage/reporting avoids float precision loss and negative-rounding errors. The new production Pulse.h extends the original pulse slope beyond 1000..2000us: signed -180/+180 (raw -90/270) request 500/2500us. Only electrical duty representation saturates, at 0..16383 for 50Hz/14-bit output. Arduino-ESP32 3.3.10 maps all-ones duty to full-on; extreme negative/positive requests can therefore produce constant LOW/HIGH. Commanded position is not physical position feedback, and software cannot extend mechanical servo travel.

Verification: 147 Python tests pass. Native production-controller/pulse tests pass with warnings treated as errors, including negative commands, signed32 extremes, overflow rejection, exact hello/hold reports, extended pulse widths, and a monotonic duty sweep. Arduino core 3.3.10 compiled the ESP32-C5 target with CDC disabled: 323,422 bytes flash and 17,804 bytes static RAM. Independent review identified a derived claw target that could overflow int32 after gain/direction; configuration now rejects such unencodable combinations, with exact boundary regressions. No travel clipping was reintroduced.

Deployment is pending current user approval under the supplied AGENTS.md workflow. The connected ESP32 still has protocol 1; the updated protocol 2 app must be started after uploading this firmware. No firmware upload or beyond-endpoint physical movement was performed in this change.

## Protocol 2 deployment confirmation

With explicit user approval, uploaded the current firmware to the identified ESP32-C5 revision 1.0 on COM70 (CH343 serial 5B90165643; base MAC 38:44:be:a5:57:50). The initial upload reused an older binary from build/esp32c5-tracking; the live handshake correctly rejected its protocol 1 response. Rebuilt current source with --clean into build/esp32c5-tracking-v2, then uploaded that binary and verified flash hashes. The fresh build reports 323,422 bytes program storage and 17,804 bytes static RAM. Application binary SHA-256: B13213DEB38C8D2D6B266210A4F5FA9B8889A63A28E1F04F275DFA07104A53E2.

The actual board now passes the protocol 2 handshake at raw positions (90,90,90,90), accepts resume and a center pose, and reports the same positions on hold. This confirms the running firmware version and serial command path; extended physical servo travel was not measured. Restarted the app on COM70/camera 1 and observed a responsive window, connected status, signed zero outputs, and paused status. Camera 1 still showed a black preview, so live gestures were not verified. Firmware deployment is complete; the earlier pending-deployment note is superseded.

## Follow-up: Camo capture and camera-switch recovery

Reproduced camera 1 returning all-black 1920x1080 frames at approximately 1fps after DirectShow width/height setters requested 960x720, despite the setters reporting success. Native DirectShow capture worked on some opens but also reproduced the black stream on later opens. Native Media Foundation capture delivered nonblack frames on three consecutive opens. Windows now prefers Media Foundation, with DirectShow fallback only when it cannot open; capture properties are left native. Frames downscale in software with preserved aspect ratio (Camo 1920x1080 becomes 960x540). Camera 1 is the supplied startup default. Genuine black frames remain valid and are not rejected based on brightness.

Camera switching now rebuilds MediaPipe only after an actual camera replacement, keeps the last preview visible during probing, and clears old model ownership before closing/replacing it. Reproduced model-constructor/cleanup failure paths no longer exit the UI or double-close a model; they show a retry status, log a traceback, retain run intent, and allow V to retry. Cleanup is idempotent and attempts both model releases and window cleanup. The user's exact disappearing-window failure was not reproduced with a native fault code; these model-lifecycle failures were reproduced with controlled boundaries and corrected.

Verification: all 159 Python tests pass. A real Camo/model smoke test processed 120 frames and exited cleanly. A full GUI test connected to COM70 performed 14 V switches between cameras 1 and 0 over 30 seconds, processed 540 frames, returned to live Camo video, and exited with code 0. No Python exception/native crash appeared in that run. The arm stayed paused during this camera test. Restarted the ordinary application on COM70/camera 1 with faulthandler enabled and local runtime logs. Camera footage and logs remain in ignored artifacts/. Firmware and servo mapping are unchanged.

## Follow-up: stronger elbow/wrist response and current-position zeros

Set the supplied IO7 elbow and IO8 wrist gains from 1 to 4. A 5-degree input change requests a 20-degree servo change before the existing smoothing/deadband. IO6 gain, claw gain, keyboard step size, and firmware are unchanged.

Calibration now captures both the current commanded servo positions and all four observed controls after the existing four-second countdown. Each captured output becomes that channel's displayed zero. Keeping the captured pose preserves every servo target, including a pinched claw; subsequent pinch control uses change in normalized closure. Recalibration replaces the zeros without recentering the robot. Keyboard steps and Session.set_position use these per-servo origins, which survive pause, camera changes, and reconnects. Restarting still clears the in-memory calibration.

All 169 Python tests pass. Coverage includes calibration from non-centre/extended positions while paused and running, no movement on capture or an unchanged pose, repeated recalibration, relative pinch, 4x elbow/wrist response using the actual project config, keyboard positions after zeroing, reconnect preservation, and signed32 boundaries. Independent review identified unencodable numeric targets after adding calibration offsets; those channels now retain valid outputs and report the encoding error without pausing or disconnecting other channels. No physical travel clamp was added.

Restarted the app on COM70/camera 1 and verified responsive live Camo video, connected status, and the new Positions (from zero) label. The board retained non-centred positions on reconnect; calibration can now use those positions as its zero. Physical gesture response under the higher gain remains for operator assessment. No firmware upload was needed.

## Follow-up: numpad servo controls

Replaced the letter-based motor keys with numpad digit pairs: 1/2 for IO6, 4/5 for IO7, 7/8 for IO8, and 3/6 for IO9. The first key subtracts five servo degrees and the second adds five. Num Lock must be on; number-row digits also work through OpenCV's character input. Existing Space, C, M, V, R, and Q/Escape controls are unchanged. The preview legend and README show the new bindings.

All 169 Python tests pass, including updated keyboard/tracking-mode regressions. An additional isolated run through the actual app key handler verified each of the eight digits independently against its requested pin and direction, without sending physical movement commands. This is a host-only remap; firmware is unchanged.

Restarted on COM70/camera 1 and verified a responsive window, live Camo video, connected status, and the numpad key legend.

## Follow-up: faster keyboard target movement

Increased all numpad servo steps from 5 to 15 nominal degrees, tripling target displacement per keypress or keyboard repeat. The existing numpad pairs, manual mode, saved calibration origins, and gesture gains are unchanged. Physical servo maximum speed and Windows keyboard repeat timing are unchanged. The UI legend reads the same KEYBOARD_STEP constant as the key bindings. All 169 Python tests pass, including updated keyboard movement and tracking-isolation assertions. Firmware is unchanged.

Restarted on COM70/camera 1. Verified live Camo video, connected status, the 15-degree numpad legend, and running keyboard mode during operator input.

## Follow-up: seven-degree steps and doubled held-key repeat

Changed servo key increments from 15 to 7 degrees. A Windows hook scoped to the app's own UI thread captures fresh presses and releases, discards native typematic duplicates, and preserves taps occurring between video frames. An elapsed-time scheduler repeats at twice the configured Windows rate, retaining the initial delay. This laptop reports speed 31 and delay 1: approximately 30 Hz native repeat and 500 ms delay, giving 60 Hz application repeat. Due increments combine into one target per channel per frame. Release, focus loss, and Space/C/M clear pending repeats; a new press can still resume normally. A stalled UI drops old repeat backlog without changing the run latch or adding joint limits. Firmware is unchanged.

All 180 Python tests pass, covering tap preservation, doubled repeat cadence, OS repeat deduplication, release, focus, mode/pause retention, stalled-frame backlog, multi-key coalescing, and helper cleanup. A separate native OpenCV window, disconnected from serial, exercised the actual Windows hook with a 0.9-second numpad hold: it recorded one initial increment plus 24 repeats after the 0.5-second delay, with no increments after release. No synthetic servo movements were sent to the board.

Restarted the full app on COM70/camera 1 and verified live Camo video, connected status, and the 7-degree numpad legend. It opened paused, retaining the board's commanded positions. Runtime logs and the own-window screenshot are in ignored artifacts/.

## Follow-up: 1.5x repeat with immediate hold response

Reduced Windows keyboard repeat from 2x to 1.5x the configured rate, retaining 7-degree increments. Removed the separate initial hold delay: the first repeat is due one regular interval after the initial press. At this laptop's setting, that is 45 increments/second and about 22 ms; actual command updates follow GUI frame timing. The app no longer reads Windows' initial repeat-delay setting.

All 180 Python tests pass, including the revised immediate-start cadence, native repeat deduplication, release handling, pause/mode changes, and dropped stale backlog. An isolated native OpenCV input test with no serial connection observed 40 increments during a 0.9-second hold, with its first repeat 31 ms after the initial step and no repeats after release. The initial smoke attempt received no input because its test window lacked focus; the focused rerun passed.

Restarted on COM70/camera 1 and verified live Camo video, connected status, and the retained 7-degree legend. Firmware is unchanged.
