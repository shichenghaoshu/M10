#include "m10_protocol_core.h"

// M10 ESP32-S3 + TB6612 pin map supplied during the 2026-08-05 hardware session.
// STBY is hard-wired high on the current chassis and is not controlled by ESP32.
// The 2026-08-05 wiring report says STBY is tied to 5 V; verify that level against
// the actual TB6612 logic VCC before powering the motor rail.
static const int STBY_PIN = -1;
static const int LEFT_PWM_PIN = 9;   // PWMA
static const int LEFT_IN1_PIN = 18;  // AIN1
static const int LEFT_IN2_PIN = 17;  // AIN2
static const int RIGHT_PWM_PIN = 10; // PWMB
static const int RIGHT_IN1_PIN = 11; // BIN1
static const int RIGHT_IN2_PIN = 12; // BIN2

// Physical acceptance on 2026-08-05 showed logical +/+ as left reverse and
// right forward. Keep logical targets symmetric and correct the left H-bridge
// polarity here so every controller (manual, remote and AI) shares one mapping.
static const bool LEFT_INVERTED = true;
static const bool RIGHT_INVERTED = false;
static const uint32_t COMMAND_WATCHDOG_MS = 300;
static const uint32_t TELEMETRY_INTERVAL_MS = 200;

struct MotorPins {
  int pwm;
  int in1;
  int in2;
  bool inverted;
};

static const MotorPins LEFT_MOTOR = {LEFT_PWM_PIN, LEFT_IN1_PIN, LEFT_IN2_PIN, LEFT_INVERTED};
static const MotorPins RIGHT_MOTOR = {RIGHT_PWM_PIN, RIGHT_IN1_PIN, RIGHT_IN2_PIN, RIGHT_INVERTED};

static_assert(LEFT_PWM_PIN != LEFT_IN1_PIN && LEFT_PWM_PIN != LEFT_IN2_PIN &&
              LEFT_PWM_PIN != RIGHT_PWM_PIN && LEFT_PWM_PIN != RIGHT_IN1_PIN &&
              LEFT_PWM_PIN != RIGHT_IN2_PIN && LEFT_IN1_PIN != LEFT_IN2_PIN &&
              LEFT_IN1_PIN != RIGHT_PWM_PIN && LEFT_IN1_PIN != RIGHT_IN1_PIN &&
              LEFT_IN1_PIN != RIGHT_IN2_PIN && LEFT_IN2_PIN != RIGHT_PWM_PIN &&
              LEFT_IN2_PIN != RIGHT_IN1_PIN && LEFT_IN2_PIN != RIGHT_IN2_PIN &&
              RIGHT_PWM_PIN != RIGHT_IN1_PIN && RIGHT_PWM_PIN != RIGHT_IN2_PIN &&
              RIGHT_IN1_PIN != RIGHT_IN2_PIN,
              "Motor control GPIOs must be unique");
static_assert(STBY_PIN < 0 ||
              (STBY_PIN != LEFT_PWM_PIN && STBY_PIN != LEFT_IN1_PIN &&
               STBY_PIN != LEFT_IN2_PIN && STBY_PIN != RIGHT_PWM_PIN &&
               STBY_PIN != RIGHT_IN1_PIN && STBY_PIN != RIGHT_IN2_PIN),
              "STBY GPIO must not overlap a motor control GPIO");

m10::StreamDecoder decoder;
int16_t leftTarget = 0;
int16_t rightTarget = 0;
bool sessionEstablished = false;
bool emergencyLatched = false;
uint32_t lastControlAtMs = 0;
uint32_t movementExpiresAtMs = 0;
uint32_t lastTelemetryAtMs = 0;
uint16_t telemetrySequence = 1;
bool hasLastExecutedCommand = false;
uint8_t lastExecutedCommandType = 0;
uint16_t lastExecutedCommandSequence = 0;

static int16_t clampTarget(int16_t target) {
  if (target > 1000) return 1000;
  if (target < -1000) return -1000;
  return target;
}

static int targetToDuty(int16_t target) {
  int magnitude = abs(static_cast<int>(clampTarget(target)));
  return (magnitude * 255 + 999) / 1000;
}

static void setStandby(bool enabled) {
  if (STBY_PIN >= 0) digitalWrite(STBY_PIN, enabled ? HIGH : LOW);
}

static void configureMotor(const MotorPins &motor) {
  pinMode(motor.pwm, OUTPUT);
  pinMode(motor.in1, OUTPUT);
  pinMode(motor.in2, OUTPUT);
  digitalWrite(motor.in1, LOW);
  digitalWrite(motor.in2, LOW);
  analogWrite(motor.pwm, 0);
}

static void setMotor(const MotorPins &motor, int16_t target) {
  int16_t output = motor.inverted ? static_cast<int16_t>(-target) : target;
  int duty = targetToDuty(output);
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

static void stopMotors() {
  leftTarget = 0;
  rightTarget = 0;
  movementExpiresAtMs = 0;
  setMotor(LEFT_MOTOR, 0);
  setMotor(RIGHT_MOTOR, 0);
  setStandby(false);
}

static void applyMotorTargets(int16_t left, int16_t right, uint16_t durationMs) {
  leftTarget = clampTarget(left);
  rightTarget = clampTarget(right);
  setStandby(leftTarget != 0 || rightTarget != 0);
  setMotor(LEFT_MOTOR, leftTarget);
  setMotor(RIGHT_MOTOR, rightTarget);
  movementExpiresAtMs = durationMs == 0 ? 0 : millis() + durationMs;
}

static void sendFrame(uint8_t type, uint16_t sequence, const uint8_t *payload,
                      uint16_t payloadLength) {
  uint8_t encoded[m10::kMaxFrameSize];
  size_t length = m10::encodeFrame(type, sequence, payload, payloadLength,
                                   encoded, sizeof(encoded));
  if (length > 0) Serial.write(encoded, length);
}

static void sendAck(uint16_t sequence) {
  uint8_t payload[2];
  m10::putLe16(payload, sequence);
  sendFrame(m10::ACK, sequence, payload, sizeof(payload));
}

static void sendFault(uint16_t code) {
  uint8_t payload[2];
  m10::putLe16(payload, code);
  sendFrame(m10::FAULT, telemetrySequence++, payload, sizeof(payload));
}

static void sendTelemetry() {
  uint8_t payload[10];
  m10::putLe16(payload + 0, static_cast<uint16_t>(leftTarget));
  m10::putLe16(payload + 2, static_cast<uint16_t>(rightTarget));
  m10::putLe16(payload + 4, 0xFFFF);  // Battery sensor not configured.
  m10::putLe16(payload + 6, 0);       // Angle sensor not configured.
  m10::putLe16(payload + 8, 0xFFFF);  // Obstacle sensor not configured.
  sendFrame(m10::TELEMETRY, telemetrySequence++, payload, sizeof(payload));
}

static bool isRepeatedCommand(const m10::Frame &frame) {
  return hasLastExecutedCommand && frame.type == lastExecutedCommandType &&
         frame.sequence == lastExecutedCommandSequence;
}

static void rememberExecutedCommand(const m10::Frame &frame) {
  hasLastExecutedCommand = true;
  lastExecutedCommandType = frame.type;
  lastExecutedCommandSequence = frame.sequence;
}

static void handleFrame(const m10::Frame &frame) {
  if (frame.version != m10::kVersion) return;

  switch (frame.type) {
    case m10::HELLO: {
      stopMotors();
      sessionEstablished = true;
      lastControlAtMs = millis();
      uint8_t capabilities[2] = {m10::kVersion, 0x01};
      sendFrame(m10::HELLO_ACK, frame.sequence, capabilities, sizeof(capabilities));
      break;
    }
    case m10::HEARTBEAT:
      if (!sessionEstablished) break;
      lastControlAtMs = millis();
      sendAck(frame.sequence);
      break;
    case m10::SET_MOTOR:
      if (isRepeatedCommand(frame)) {
        sendAck(frame.sequence);
        break;
      }
      if (!sessionEstablished || emergencyLatched || frame.payloadLength != 7) {
        stopMotors();
        if (emergencyLatched) sendFault(0x0001);
        break;
      }
      lastControlAtMs = millis();
      applyMotorTargets(m10::getSignedLe16(frame.payload + 0),
                        m10::getSignedLe16(frame.payload + 2),
                        m10::getLe16(frame.payload + 4));
      rememberExecutedCommand(frame);
      sendAck(frame.sequence);
      break;
    case m10::STOP:
      if (isRepeatedCommand(frame)) {
        sendAck(frame.sequence);
        break;
      }
      stopMotors();
      if (sessionEstablished) {
        lastControlAtMs = millis();
        rememberExecutedCommand(frame);
        sendAck(frame.sequence);
      }
      break;
    case m10::EMERGENCY_STOP:
      if (isRepeatedCommand(frame)) {
        sendAck(frame.sequence);
        break;
      }
      emergencyLatched = true;
      stopMotors();
      rememberExecutedCommand(frame);
      sendAck(frame.sequence);
      break;
    case m10::CLEAR_EMERGENCY_STOP:
      if (isRepeatedCommand(frame)) {
        sendAck(frame.sequence);
        break;
      }
      stopMotors();
      if (sessionEstablished) {
        emergencyLatched = false;
        lastControlAtMs = millis();
        rememberExecutedCommand(frame);
        sendAck(frame.sequence);
      }
      break;
    case m10::PING:
      if (sessionEstablished) sendFrame(m10::PONG, frame.sequence, frame.payload,
                                        frame.payloadLength);
      break;
    default:
      break;
  }
}

static void readProtocol() {
  m10::Frame frame;
  while (Serial.available() > 0) {
    int incoming = Serial.read();
    if (incoming >= 0 && decoder.append(static_cast<uint8_t>(incoming), &frame)) {
      handleFrame(frame);
    }
  }
}

static void enforceSafety() {
  uint32_t now = millis();
  bool moving = leftTarget != 0 || rightTarget != 0;
  if (moving && (!sessionEstablished || now - lastControlAtMs > COMMAND_WATCHDOG_MS)) {
    stopMotors();
  }
  if (moving && movementExpiresAtMs != 0 &&
      static_cast<int32_t>(now - movementExpiresAtMs) >= 0) {
    stopMotors();
  }
}

void setup() {
  if (STBY_PIN >= 0) {
    pinMode(STBY_PIN, OUTPUT);
    setStandby(false);
  }
  configureMotor(LEFT_MOTOR);
  configureMotor(RIGHT_MOTOR);
  stopMotors();
  Serial.begin(115200);
  lastControlAtMs = millis();
  lastTelemetryAtMs = millis();
}

void loop() {
  readProtocol();
  enforceSafety();
  uint32_t now = millis();
  if (sessionEstablished && now - lastTelemetryAtMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryAtMs = now;
    sendTelemetry();
  }
}
