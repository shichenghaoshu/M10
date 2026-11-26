# R3X Two-Wheel Differential Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Drive a WHEELTEC R3X four-wheel two-drive differential chassis from an ESP32-S3, controlled by the Linux host over USB serial.

**Architecture:** Keep the Linux protocol as newline-terminated text commands because `m10-robot-core` already sends `forward`, `backward`, `left`, `right`, `stop`, `status`, and `heartbeat`. On the ESP32, treat the chassis as two differential drive motors: one left drive motor and one right drive motor. Start with open-loop PWM and leave encoder PID as the next hardware-calibration phase.

**Tech Stack:** Arduino ESP32 core, ESP32-S3 DevKitC-1, TB6612FNG-compatible dual H-bridge modules, USB serial at 115200 baud, Python `pyserial` host test script.

---

### Task 1: Motion Mapping Test

**Files:**
- Create: `tests/test_motor_control_core.cpp`
- Create: `esp32/motor_serial_test/motor_control_core.h`

**Step 1:** Write a failing C++ test for text command to signed left/right motor outputs.

**Step 2:** Run `g++ -std=c++17 -Wall -Wextra -pedantic tests/test_motor_control_core.cpp -o /tmp/test_motor_control_core && /tmp/test_motor_control_core` and confirm it fails because the core header is missing.

**Step 3:** Add the minimal pure C++ core header.

**Step 4:** Re-run the command and confirm it passes.

### Task 2: ESP32 Firmware

**Files:**
- Modify: `esp32/motor_serial_test/motor_serial_test.ino`

**Step 1:** Use `motor_control_core.h` in the Arduino sketch.

**Step 2:** Configure two motor channels: left drive and right drive.

**Step 3:** Accept line commands, apply the differential mapping, acknowledge commands, and stop on command timeout.

**Step 4:** Compile with `arduino-cli` when available. If it is unavailable, run the C++ core test as the local verification gate.

### Task 3: Wiring and Host Control Docs

**Files:**
- Modify: `docs/wiring.md`
- Modify: `README.md`
- Modify: `docs/test_plan.md`

**Step 1:** Document ESP32-to-TB6612 signal wiring, motor output wiring, power rails, and USB serial connection to Linux.

**Step 2:** Document Linux commands for `serial_control_test.py` and `m10-robot-core`.

**Step 3:** Re-run text/core checks.
