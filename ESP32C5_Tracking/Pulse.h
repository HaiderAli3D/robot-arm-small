#pragma once
#include <stdint.h>

namespace robot_arm {
constexpr uint32_t PWM_HZ = 50;
constexpr uint8_t PWM_BITS = 14;
// Arduino-ESP32 3.3.10 maps this all-ones duty to full-on internally.
constexpr uint32_t PWM_MAX_DUTY = (1u << PWM_BITS) - 1u;
constexpr double PWM_PERIOD_US = 1000000.0 / PWM_HZ;

// Raw angle 90 means center. No servo travel limit is applied. Only the
// electrical PWM period/duty representation bounds the output waveform.
inline double pulseMicroseconds(int32_t angle) {
  const double requested = 1000.0 + double(angle) * (1000.0 / 180.0);
  if (requested <= 0.0) return 0.0;
  if (requested >= PWM_PERIOD_US) return PWM_PERIOD_US;
  return requested;
}

inline uint32_t pulseDuty(int32_t angle) {
  const double requested = pulseMicroseconds(angle) * (1u << PWM_BITS) / PWM_PERIOD_US;
  // Clamp before any float-to-unsigned conversion, including rounding at the
  // maximum. Neither negative input nor int32 extremes can wrap the duty.
  if (requested >= double(PWM_MAX_DUTY)) return PWM_MAX_DUTY;
  if (requested <= 0.0) return 0;
  return uint32_t(requested + 0.5);
}
} // namespace robot_arm
