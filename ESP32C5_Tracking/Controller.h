#pragma once
// Production parser/controller, independent of Arduino and heap allocation.
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

namespace robot_arm {
class Controller {
 public:
  typedef void (*Reply)(void*, const char*);
  typedef void (*Output)(void*, unsigned, float, bool);
  Controller(Reply reply, Output output, void* context)
      : reply_(reply), output_(output), context_(context) {}
  void begin(uint32_t now) {
    resumed_ = false; length_ = 0; lineError_ = nullptr; carriageReturn_ = false;
    lastUpdate_ = now;
    for (unsigned i = 0; i < 4; ++i) {
      current_[i] = target_[i] = 90.0f; enabled_[i] = true;
      output_(context_, i, current_[i], true);
    }
    reportAngles("ROBOT_ARM 1");
  }
  void tick(uint32_t now) {
    if (uint32_t(now - lastUpdate_) < 20) return;
    lastUpdate_ = now;
    // Apply requested positions directly on each 50Hz output update.
    for (unsigned i = 0; i < 4; ++i) {
      current_[i] = target_[i];
      output_(context_, i, current_[i], enabled_[i]);
    }
  }
  void receive(char character, uint32_t now) {
    const unsigned char c = static_cast<unsigned char>(character);
    if (c == '\n') {
      if (lineError_) reply_(context_, lineError_);
      else { buffer_[length_] = '\0'; command(now); }
      length_ = 0; lineError_ = nullptr; carriageReturn_ = false;
      return;
    }
    if (lineError_) return; // Drain entire invalid line before accepting again.
    if (carriageReturn_) { lineError_ = "ERR invalid_character"; return; }
    if (c == '\r') { carriageReturn_ = true; return; }
    if ((c < 32 && c != '\t') || c > 126) { lineError_ = "ERR invalid_character"; return; }
    if (length_ == 95) { lineError_ = "ERR line_too_long"; return; }
    buffer_[length_++] = character;
  }
 private:
  Reply reply_;
  Output output_;
  void* context_;
  float current_[4] = {90, 90, 90, 90}, target_[4] = {90, 90, 90, 90};
  bool enabled_[4] = {true, true, true, true}, resumed_ = false;
  uint32_t lastUpdate_ = 0;
  char buffer_[96] = {};
  size_t length_ = 0;
  const char* lineError_ = nullptr;
  bool carriageReturn_ = false;
  void freeze() {
    resumed_ = false;
    for (unsigned i = 0; i < 4; ++i) target_[i] = current_[i];
  }
  void reportAngles(const char* prefix) {
    char response[64];
    snprintf(response, sizeof(response), "%s %d %d %d %d", prefix,
             int(current_[0] + 0.5f), int(current_[1] + 0.5f),
             int(current_[2] + 0.5f), int(current_[3] + 0.5f));
    reply_(context_, response);
  }
  static bool angle(const char* token, int& value) {
    if (!*token) return false;
    value = 0;
    for (; *token; ++token) {
      if (*token < '0' || *token > '9') return false;
      // Value was <=180 before multiplication: cannot overflow.
      value = value * 10 + (*token - '0');
      if (value > 180) return false;
    }
    return true;
  }
  void command(uint32_t now) {
    char* fields[6]; unsigned count = 0; char* cursor = buffer_;
    while (*cursor) {
      while (*cursor == ' ' || *cursor == '\t') ++cursor;
      if (!*cursor) break;
      if (count == 6) { reply_(context_, "ERR fields"); return; }
      fields[count++] = cursor;
      while (*cursor && *cursor != ' ' && *cursor != '\t') ++cursor;
      if (*cursor) *cursor++ = '\0';
    }
    if (count == 0) return;
    const char* name = fields[0];
    if (strcmp(name, "pose") == 0) {
      int values[4];
      if (count != 5) { reply_(context_, "ERR fields"); return; }
      for (unsigned i = 0; i < 4; ++i) {
        if (!angle(fields[i+1], values[i])) { reply_(context_, "ERR angle"); return; }
      }
      if (!resumed_) { reply_(context_, "ERR paused"); return; }
      for (unsigned i = 0; i < 4; ++i) { target_[i] = float(values[i]); enabled_[i] = true; }
      reply_(context_, "OK pose"); return;
    }
    if (count == 1 && strcmp(name, "hello") == 0) { freeze(); reportAngles("ROBOT_ARM 1"); return; }
    if (count == 1 && strcmp(name, "hold") == 0) { freeze(); reportAngles("OK hold"); return; }
    if (count == 1 && strcmp(name, "resume") == 0) {
      freeze(); resumed_ = true; lastUpdate_ = now;
      reply_(context_, "OK resume"); return;
    }
    if (count == 1 && strcmp(name, "help") == 0) {
      reply_(context_, "Commands: hello | resume | pose a6 a7 a8 a9 | hold | 1..4 angle | all angle | 1..4 off | off | help");
      return;
    }
    const bool single = name[0] >= '1' && name[0] <= '4' && name[1] == '\0';
    const bool all = strcmp(name, "all") == 0;
    if ((count == 1 && strcmp(name, "off") == 0) ||
        (count == 2 && single && strcmp(fields[1], "off") == 0)) {
      freeze();
      for (unsigned i = 0; i < 4; ++i) {
        if (count == 1 || i == unsigned(name[0] - '1')) {
          enabled_[i] = false; output_(context_, i, current_[i], false);
        }
      }
      reply_(context_, "OK off"); return;
    }
    int value;
    if (count == 2 && (single || all) && angle(fields[1], value)) {
      freeze();
      for (unsigned i = 0; i < 4; ++i) {
        if (all || i == unsigned(name[0] - '1')) { target_[i] = float(value); enabled_[i] = true; }
      }
      reply_(context_, "OK manual"); return;
    }
    reply_(context_, "ERR command");
  }
};
} // namespace robot_arm
