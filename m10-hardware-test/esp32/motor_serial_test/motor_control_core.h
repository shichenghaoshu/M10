#ifndef M10_MOTOR_CONTROL_CORE_H
#define M10_MOTOR_CONTROL_CORE_H

#include <ctype.h>
#include <stddef.h>
#include <string.h>

static const int kForwardPwm = 180;
static const int kTurnPwm = 160;
static const int kMaxPwm = 255;

struct MotionCommand {
  bool valid;
  int left;
  int right;
  const char *name;
  bool movement;
};

inline int clampPwm(int pwm) {
  if (pwm > kMaxPwm) {
    return kMaxPwm;
  }
  if (pwm < -kMaxPwm) {
    return -kMaxPwm;
  }
  return pwm;
}

inline bool commandEquals(const char *actual, const char *expected) {
  if (actual == NULL || expected == NULL) {
    return false;
  }

  while (*actual != '\0' && isspace(static_cast<unsigned char>(*actual))) {
    actual++;
  }

  while (*actual != '\0' && *expected != '\0') {
    char a = static_cast<char>(tolower(static_cast<unsigned char>(*actual)));
    char e = static_cast<char>(tolower(static_cast<unsigned char>(*expected)));
    if (a != e) {
      return false;
    }
    actual++;
    expected++;
  }

  while (*actual != '\0' && isspace(static_cast<unsigned char>(*actual))) {
    actual++;
  }

  return *actual == '\0' && *expected == '\0';
}

inline MotionCommand makeMotion(bool valid, int left, int right, const char *name, bool movement) {
  MotionCommand motion = {valid, clampPwm(left), clampPwm(right), name, movement};
  return motion;
}

inline MotionCommand motionFromCommand(const char *command) {
  if (commandEquals(command, "forward")) {
    return makeMotion(true, kForwardPwm, kForwardPwm, "forward", true);
  }
  if (commandEquals(command, "backward")) {
    return makeMotion(true, -kForwardPwm, -kForwardPwm, "backward", true);
  }
  if (commandEquals(command, "left")) {
    return makeMotion(true, -kTurnPwm, kTurnPwm, "left", true);
  }
  if (commandEquals(command, "right")) {
    return makeMotion(true, kTurnPwm, -kTurnPwm, "right", true);
  }
  if (commandEquals(command, "stop")) {
    return makeMotion(true, 0, 0, "stop", false);
  }
  if (commandEquals(command, "status")) {
    return makeMotion(true, 0, 0, "status", false);
  }
  if (commandEquals(command, "heartbeat")) {
    return makeMotion(true, 0, 0, "heartbeat", false);
  }

  return makeMotion(false, 0, 0, "unknown", false);
}

#endif
