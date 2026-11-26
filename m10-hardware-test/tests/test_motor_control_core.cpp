#include <cassert>
#include <cstring>

#include "../esp32/motor_serial_test/motor_control_core.h"

static void expect_motion(const char *command, int left, int right, const char *name) {
  MotionCommand motion = motionFromCommand(command);
  assert(motion.valid);
  assert(motion.left == left);
  assert(motion.right == right);
  assert(std::strcmp(motion.name, name) == 0);
}

int main() {
  expect_motion("forward", 180, 180, "forward");
  expect_motion("backward", -180, -180, "backward");
  expect_motion("left", -160, 160, "left");
  expect_motion("right", 160, -160, "right");
  expect_motion("stop", 0, 0, "stop");
  expect_motion("heartbeat", 0, 0, "heartbeat");

  MotionCommand unknown = motionFromCommand("spin");
  assert(!unknown.valid);
  assert(unknown.left == 0);
  assert(unknown.right == 0);

  MotionCommand empty = motionFromCommand("");
  assert(!empty.valid);
  assert(empty.left == 0);
  assert(empty.right == 0);

  assert(clampPwm(300) == 255);
  assert(clampPwm(-300) == -255);
  assert(clampPwm(42) == 42);

  return 0;
}
