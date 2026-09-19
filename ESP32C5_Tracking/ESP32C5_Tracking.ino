/*
  Waveshare ESP32-C5-WIFI6-KIT-N16R4; USB-C UART, 115200 baud.
  ESP32C5 Dev Module, Espressif core 3.3.10, USB CDC On Boot Disabled.
  GPIO6/7/8/9 are servo 1/2/3/4. All boot at nominal 90 degrees.
  Positional MG90S: 1000..2000us at 50Hz, not calibrated physical degrees.
  Boot can move the mechanism because its actual position is unknown.

  Supply servos directly from an appropriately sized regulated 5V supply;
  common GND with ESP32. Do not join external +5V and USB +5V rails.
  "off" disables pulses only: electrical power remains connected and holding
  torque may be lost. It is not an emergency power disconnect.

  Newline commands: hello, resume, pose a6 a7 a8 a9, hold,
  1 90, all 90, 2 off, off, help. Angles are absolute nominal degrees.
  This is the camera tracking firmware. The separate ESP32C5_FourServos
  relative-command sample is preserved and is not the tracking target.
*/
#include <Arduino.h>
#include "Controller.h"

constexpr uint8_t SERVO_PINS[4] = {6, 7, 8, 9};
constexpr uint32_t PWM_HZ = 50;
constexpr uint8_t PWM_BITS = 14;
bool attached[4] = {false, false, false, false};
bool hardwareFault = false;

void stopPulses() {
  for (unsigned i = 0; i < 4; ++i) {
    if (attached[i]) ledcWrite(SERVO_PINS[i], 0);
  }
}

void reply(void*, const char* response) {
  if (!hardwareFault) Serial.println(response);
}

void output(void*, unsigned index, float angle, bool enabled) {
  if (hardwareFault) return;
  const uint32_t pulseUs = uint32_t(1000.0f + angle * (1000.0f / 180.0f) + 0.5f);
  const uint32_t duty = enabled
      ? uint32_t((uint64_t(pulseUs) * (1UL << PWM_BITS) * PWM_HZ + 500000) / 1000000)
      : 0;
  if (!attached[index] || !ledcWrite(SERVO_PINS[index], duty)) {
    hardwareFault = true;
    stopPulses();
    Serial.println("ERR hardware");
  }
}

robot_arm::Controller controller(reply, output, nullptr);

void setup() {
  Serial.begin(115200);
  for (unsigned i = 0; i < 4; ++i) {
    pinMode(SERVO_PINS[i], OUTPUT);
    digitalWrite(SERVO_PINS[i], LOW);
    attached[i] = ledcAttach(SERVO_PINS[i], PWM_HZ, PWM_BITS);
    if (!attached[i]) hardwareFault = true;
  }
  if (hardwareFault) { stopPulses(); Serial.println("ERR hardware"); }
  else controller.begin(millis());
}

void loop() {
  // Bound each batch so sustained serial input cannot starve output ticks.
  for (unsigned n = 0; n < 128 && Serial.available() > 0; ++n) {
    const char c = char(Serial.read());
    if (hardwareFault) { if (c == '\n') Serial.println("ERR hardware"); }
    else controller.receive(c, millis());
  }
  if (!hardwareFault) controller.tick(millis());
  delay(1);
}
