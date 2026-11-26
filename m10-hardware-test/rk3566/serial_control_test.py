#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import serial

DEFAULT_BAUDRATE = 115200
DEFAULT_DEVICES = ("/dev/ttyUSB0", "/dev/ttyACM0")
VALID_COMMANDS = ("forward", "backward", "left", "right", "stop", "status", "heartbeat")


def choose_serial_device(manual_device: Optional[str]) -> str:
    if manual_device:
        return manual_device

    for device in DEFAULT_DEVICES:
        if Path(device).exists():
            return device

    raise FileNotFoundError(
        "No serial device found. Checked /dev/ttyUSB0 and /dev/ttyACM0. "
        "Connect the ESP32 or pass --device explicitly."
    )


def send_command(port: serial.Serial, command: str) -> str:
    port.write((command + "\n").encode("utf-8"))
    port.flush()
    time.sleep(0.1)

    deadline = time.time() + 1.5
    lines: list[str] = []
    while time.time() < deadline:
        raw = port.readline()
        if not raw:
            continue
        decoded = raw.decode("utf-8", errors="replace").strip()
        if decoded:
            lines.append(decoded)
        if port.in_waiting == 0 and lines:
            break

    return "\n".join(lines) if lines else "(no response)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Send motion commands from RK3566 to ESP32.")
    parser.add_argument("--device", help="Serial device path, for example /dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="Serial baudrate")
    args = parser.parse_args()

    try:
        device = choose_serial_device(args.device)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        with serial.Serial(device, args.baudrate, timeout=0.5) as port:
            time.sleep(2.0)
            print(f"Connected to {device} at {args.baudrate} baud.")
            print(f"Supported commands: {', '.join(VALID_COMMANDS)}")
            print("Type 'quit' or 'exit' to stop.")

            while True:
                try:
                    command = input("m10> ").strip().lower()
                except EOFError:
                    print()
                    break

                if command in {"quit", "exit"}:
                    break
                if not command:
                    continue
                if command not in VALID_COMMANDS:
                    print(f"ERROR: Unsupported command '{command}'.")
                    continue

                response = send_command(port, command)
                print(f"ESP32: {response}")
    except serial.SerialException as exc:
        print(f"ERROR: Failed to open or use serial device {device}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
