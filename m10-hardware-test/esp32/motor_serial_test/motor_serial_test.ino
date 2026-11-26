#include "motor_control_core.h"

struct MotorPins {
  const char *name;
  int pwm;
  int in1;
  int in2;
  bool inverted;
};

// R3X four-wheel two-drive differential chassis: one left drive motor and one right drive motor.
// Adjust these GPIOs if your ESP32-S3 carrier board reserves any of them.
static const int STBY_PIN = 12;
static const MotorPins LEFT_DRIVE = {"left_drive", 4, 5, 6, false};
static const MotorPins RIGHT_DRIVE = {"right_drive", 7, 15, 16, false};

static const unsigned long COMMAND_TIMEOUT_MS = 1000;

String inputBuffer;
unsigned long lastMovementCommandMs = 0;
MotionCommand currentMotion = makeMotion(true, 0, 0, "stop", false);

void setMotor(const MotorPins &motor, int signedPwm) {
  int output = motor.inverted ? -signedPwm : signedPwm;
  int duty = abs(clampPwm(output));

  if (duty == 0) {
    digitalWrite(motor.in1, LOW);
    digitalWrite(motor.in2, LOW);
    analogWrite(motor.pwm, 0);
    return;
  }

  digitalWrite(motor.in1, output > 0 ? HIGH : LOW);
  digitalWrite(motor.in2, output > 0 ? LOW : HIGH);
  analogWrite(motor.pwm, duty);
}

void applyDifferentialMotion(const MotionCommand &motion) {
  digitalWrite(STBY_PIN, HIGH);
  setMotor(LEFT_DRIVE, motion.left);
  setMotor(RIGHT_DRIVE, motion.right);
  currentMotion = motion;
}

void stopMotors() {
  applyDifferentialMotion(makeMotion(true, 0, 0, "stop", false));
}

void configureMotorPins(const MotorPins &motor) {
  pinMode(motor.pwm, OUTPUT);
  pinMode(motor.in1, OUTPUT);
  pinMode(motor.in2, OUTPUT);
  setMotor(motor, 0);
}

void configurePins() {
  pinMode(STBY_PIN, OUTPUT);
  digitalWrite(STBY_PIN, HIGH);

  configureMotorPins(LEFT_DRIVE);
  configureMotorPins(RIGHT_DRIVE);
  stopMotors();
}

void printStatus() {
  Serial.print("STATUS mode=");
  Serial.print(currentMotion.name);
  Serial.print(" left=");
  Serial.print(currentMotion.left);
  Serial.print(" right=");
  Serial.print(currentMotion.right);
  Serial.println(" battery=unknown chassis=r3x_two_drive_diff");
}

void handleCommand(const String &line) {
  MotionCommand motion = motionFromCommand(line.c_str());

  if (!motion.valid) {
    stopMotors();
    Serial.println("ERR unknown_command");
    return;
  }

  if (commandEquals(line.c_str(), "status")) {
    printStatus();
    return;
  }

  if (commandEquals(line.c_str(), "heartbeat")) {
    Serial.println("OK heartbeat");
    return;
  }

  applyDifferentialMotion(motion);

  if (motion.movement) {
    lastMovementCommandMs = millis();
  }

  Serial.print("OK ");
  Serial.println(motion.name);
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char incoming = static_cast<char>(Serial.read());
    if (incoming == '\n' || incoming == '\r') {
      if (inputBuffer.length() > 0) {
        handleCommand(inputBuffer);
        inputBuffer = "";
      }
    } else if (inputBuffer.length() < 64) {
      inputBuffer += incoming;
    } else {
      inputBuffer = "";
      stopMotors();
      Serial.println("ERR command_too_long");
    }
  }
}

void enforceCommandTimeout() {
  if (currentMotion.movement && millis() - lastMovementCommandMs > COMMAND_TIMEOUT_MS) {
    stopMotors();
    Serial.println("OK stop timeout");
  }
}

void setup() {
  Serial.begin(115200);
  configurePins();
  inputBuffer.reserve(64);
  lastMovementCommandMs = millis();
  Serial.println("M10 R3X two-drive differential motor controller ready");
}

void loop() {
  readSerialCommands();
  enforceCommandTimeout();
}
