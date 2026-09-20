/*
  ESP32-C5 four-servo serial controller - RELATIVE-CW-v4
  Board: Waveshare ESP32-C5-WIFI6-KIT-N16R4
  Arduino IDE: ESP32C5 Dev Module, current Espressif ESP32 core.
  Plug into USB-C labelled UART. USB CDC On Boot: Disabled.
  Open Tools > Serial Monitor: 115200 baud, Newline.
  Type a command into the message field and press Enter.

  Signals: servo 1 = GPIO6; 2 = GPIO7; 3 = GPIO8; 4 = GPIO9.
  All four channels are enabled; no configuration change is needed.
  All signals stay LOW until a command is sent.

  Commands:
    center   command all four servos to centre and establish zero
    1 center command only servo 1 to centre and establish zero
    1 45     move servo 1 another 45 degrees clockwise
    1 45     move it another 45 clockwise (total +90 from centre)
    1 -45    move it 45 degrees anticlockwise (total +45 from centre)
    2 +10    add 10 degrees to servo 2's last commanded position
    all -5   subtract 5 degrees from each servo's own position
    status   report last commanded positions (not measured positions)
    2 off    stop pulses on servo 2
    off      stop pulses on all servos
    help     show instructions

  Each servo keeps receiving its last position command until changed or
  switched off. 'off' stops pulses, not electrical power, and may release
  holding torque. This is not an emergency power disconnect.

  POWER: four MG90S servos need an appropriately sized regulated 5V supply
  wired directly to their red leads, with common GND to the ESP32.
  Do not assume the board's 5V pin can power all four. Moving only one
  at a time does not eliminate holding current in the other servos.
  With external servo power and USB, do not join the two +5V rails.

  Use positional MG90S servos. -90..+90 is mapped to a conservative
  1000..2000 us pulse range at 50Hz, not calibrated physical degrees.
  Stored position zero means centre (1500 us). Numeric commands are
  RELATIVE CHANGES: a numeric 0 does nothing; use 'center' to centre.
  First nonzero movement after boot/off automatically centres that servo,
  waits 500 ms, then applies the requested change. This wait is not feedback.
  Position tracking uses the last successful command, not shaft feedback.
  Positive movement means clockwise when looking directly at the output
  shaft. Pulse direction varies between servos: test a small move and
  change that motor's CLOCKWISE_SIGN to -1 if +10 moves anticlockwise.
  The defaults assume that increasing pulse width produces clockwise
  movement. This physical direction cannot be detected by the ESP32.
  MIN_PULSE_US/MAX_PULSE_US are conservative starting values. Calibrate
  the pulse endpoints for your servo to make commanded degrees match
  measured degrees. Do not force a servo against a mechanical stop.
  Re-centre after manually moving the mechanism or cycling servo power.
  All valid integer movement amounts are accepted; there is no delta limit.
  Output travel is still bounded to the configured pulse endpoints (-90..+90
  in nominal coordinates). Excess movement is clipped and explicitly reported.
  Tracking stores the output target, not the unreachable requested position,
  so reversing direction works immediately after reaching an endpoint.
  Hardware errors and malformed commands are still reported honestly.
  The first move can jump because the actual position is unknown.
  Continuous-rotation servos interpret these pulses as speed/direction.

  Uses built-in LEDC; no third-party servo library required.
*/

#include <Arduino.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

constexpr uint8_t SERVO_PINS[4] = {6, 7, 8, 9};
constexpr uint32_t PWM_HZ = 50;
constexpr uint8_t PWM_BITS = 14;
constexpr uint32_t MIN_PULSE_US = 1000;
constexpr uint32_t MAX_PULSE_US = 2000;
// Motor order: 1, 2, 3, 4. Flip a sign if that motor's + move is anticlockwise.
// Defines direction viewed straight at the servo output shaft, not behind it.
int8_t CLOCKWISE_SIGN[4] = {+1, +1, +1, +1};

bool attached[4] = {false, false, false, false};
int commandedAngle[4] = {0, 0, 0, 0};
bool positionEstablished[4] = {false, false, false, false};
char commandBuffer[96];
size_t commandLength = 0;
bool discardLine = false;

void stopPulses() {
  for (int i = 0; i < 4; ++i) {
    if (attached[i]) ledcWrite(SERVO_PINS[i], 0);
    positionEstablished[i] = false;
  }
}

void printHelp() {
  Serial.println("\nFirmware: RELATIVE-CW-v4");
  Serial.println("\nAll four servos enabled: 1=GPIO6, 2=GPIO7, 3=GPIO8, 4=GPIO9.");
  Serial.println("Positive = move clockwise; negative = move anticlockwise (check CLOCKWISE_SIGN).");
  Serial.println("1 45 then 1 45 = +90 total. Every numeric command is an amount to move.");
  Serial.println("First nonzero movement after boot/off automatically centres that motor.");
  Serial.println("Commands: <servo> <delta>, all <delta>, <servo> center/off, center, off, status, help");
  Serial.println("Movement amounts accepted without angle rejection; output stops at configured endpoints.");
  Serial.println("Numeric 0 does nothing. Endpoint clipping is reported; it does not add pending movement.");
}

bool setServoAngle(int index, int angle) {
  if (index < 0 || index >= 4) {
    Serial.println("Servo must be 1..4.");
    return false;
  }
  if (!attached[index]) {
    Serial.printf("Servo %d unavailable: PWM setup failed.\n", index + 1);
    return false;
  }
  if (CLOCKWISE_SIGN[index] != 1 && CLOCKWISE_SIGN[index] != -1) {
    Serial.println("CLOCKWISE_SIGN must be +1 or -1.");
    return false;
  }
  // Bound output to configured endpoints; never extrapolate arbitrary pulses.
  if (angle < -90) angle = -90;
  if (angle > 90) angle = 90;
  const int pulseAngle = angle * CLOCKWISE_SIGN[index];
  const uint32_t pulseUs = MIN_PULSE_US +
      (uint32_t(pulseAngle + 90) * (MAX_PULSE_US - MIN_PULSE_US) + 90) / 180;
  const uint32_t duty = (uint64_t(pulseUs) * (1UL << PWM_BITS) * PWM_HZ + 500000) / 1000000;
  if (!ledcWrite(SERVO_PINS[index], duty)) {
    Serial.println("PWM write failed.");
    return false;
  }
  commandedAngle[index] = angle;
  positionEstablished[index] = true;
  Serial.printf("Servo %d (GPIO%d): commanded position %d deg, %lu us\n",
                index + 1, SERVO_PINS[index], angle, (unsigned long)pulseUs);
  return true;
}

void printStatus() {
  for (int i = 0; i < 4; ++i) {
    if (!attached[i]) Serial.printf("Servo %d: PWM unavailable.\n", i + 1);
    else if (!positionEstablished[i]) Serial.printf("Servo %d: idle; next nonzero move will centre first.\n", i + 1);
    else Serial.printf("Servo %d: last commanded position %d deg (not measured).\n", i + 1, commandedAngle[i]);
  }
}

bool moveByDegrees(int index, long long change) {
  if (index < 0 || index >= 4) return false;
  if (!attached[index]) {
    Serial.printf("Motor %d: hardware error, PWM unavailable.\n", index + 1);
    return false;
  }
  if (change == 0) {
    Serial.printf("Motor %d: zero change; no movement.\n", index + 1);
    return true;
  }
  if (!positionEstablished[index]) {
    Serial.printf("Motor %d: centring first, then applying change.\n", index + 1);
    if (!setServoAngle(index, 0)) return false;
    delay(500);
  }
  const int previous = commandedAngle[index];
  // Compare before adding, so even LLONG_MIN/MAX cannot overflow.
  const int next = change > 90 - previous ? 90 :
                   change < -90 - previous ? -90 : previous + int(change);
  const int applied = next - previous;
  if (applied != 0 && !setServoAngle(index, next)) return false;
  Serial.printf("Motor %d: requested %+lld deg; commanded %+d deg; position %d -> %d.\n",
                index + 1, change, applied, previous, next);
  if (change != applied) {
    Serial.println("Configured output endpoint reached; excess movement discarded.");
  }
  return true;
}

void handleCommand(const char *line) {
  char motor[8] = {}, value[80] = {}, extra;
  const int fields = sscanf(line, "%7s %79s %c", motor, value, &extra);
  if (fields < 1) return;
  if (fields == 1 && strcmp(motor, "help") == 0) { printHelp(); return; }
  if (fields == 1 && strcmp(motor, "status") == 0) { printStatus(); return; }
  if (fields == 1 && strcmp(motor, "center") == 0) {
    for (int i = 0; i < 4; ++i) setServoAngle(i, 0);
    return;
  }
  if (fields == 1 && strcmp(motor, "off") == 0) {
    stopPulses();
    Serial.println("Control pulses stopped. Power remains connected. Next nonzero move will centre first.");
    return;
  }
  if (fields == 2 && motor[0] >= '1' && motor[0] <= '4' &&
      motor[1] == '\0' && strcmp(value, "off") == 0) {
    const int index = motor[0] - '1';
    if (attached[index]) ledcWrite(SERVO_PINS[index], 0);
    positionEstablished[index] = false;
    Serial.printf("Servo %d pulses stopped; power remains connected. Next nonzero move will centre first.\n", index + 1);
    return;
  }
  if (fields == 2 && strcmp(value, "center") == 0) {
    if (strcmp(motor, "all") == 0) {
      for (int i = 0; i < 4; ++i) setServoAngle(i, 0);
    } else if (motor[0] >= '1' && motor[0] <= '4' && motor[1] == '\0') {
      setServoAngle(motor[0] - '1', 0);
    } else Serial.println("Servo must be 1, 2, 3, 4 or all.");
    return;
  }
  char *end = nullptr;
  // Excessively large integer tokens saturate in strtoll; their sign still
  // selects the appropriate endpoint. Malformed tokens are not movement commands.
  const long long delta = strtoll(value, &end, 10);
  if (fields != 2 || end == value || *end != '\0') {
    Serial.println("Expected an integer movement, e.g. 1 -30 or all +10.");
    return;
  }
  if (strcmp(motor, "all") == 0) {
    for (int i = 0; i < 4; ++i) moveByDegrees(i, delta);
  } else if (motor[0] >= '1' && motor[0] <= '4' && motor[1] == '\0') {
    const int index = motor[0] - '1';
    moveByDegrees(index, delta);
  } else {
    Serial.println("Servo must be 1, 2, 3, 4 or all.");
  }
}

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < 4; ++i) {
    pinMode(SERVO_PINS[i], OUTPUT);
    digitalWrite(SERVO_PINS[i], LOW);
    attached[i] = ledcAttach(SERVO_PINS[i], PWM_HZ, PWM_BITS);
    if (attached[i]) ledcWrite(SERVO_PINS[i], 0);
    else Serial.printf("ERROR: cannot configure PWM on GPIO%d.\n", SERVO_PINS[i]);
  }
  printHelp();
}

void loop() {
  while (Serial.available() > 0) {
    const char c = char(Serial.read());
    if (c == '\r' || c == '\n') {
      if (discardLine) Serial.println("Command too long; discarded.");
      else {
        commandBuffer[commandLength] = '\0';
        handleCommand(commandBuffer);
      }
      commandLength = 0;
      discardLine = false;
    } else if (!discardLine) {
      if (commandLength < sizeof(commandBuffer) - 1) commandBuffer[commandLength++] = c;
      else discardLine = true;
    }
  }
  delay(1);
}
