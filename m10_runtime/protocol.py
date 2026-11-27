"""M10 V2 wire format matching the public ESP32 firmware."""
from __future__ import annotations

import struct
import time

HELLO, HELLO_ACK, HEARTBEAT, ACK = 0x01, 0x02, 0x03, 0x04
SET_MOTOR, STOP, ESTOP, CLEAR_ESTOP = 0x10, 0x11, 0x12, 0x13
TELEMETRY, FAULT = 0x20, 0x22


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def frame(kind: int, sequence: int, payload: bytes = b"") -> bytes:
    if len(payload) > 256:
        raise ValueError("Payload too large")
    body = struct.pack("<BBHH", 2, kind, sequence & 0xFFFF, len(payload)) + payload
    return b"\xaa\x55" + body + struct.pack("<H", crc16(body))


class Decoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, int, bytes]]:
        self.buffer.extend(data)
        result = []
        while self.buffer:
            pos = self.buffer.find(b"\xaa\x55")
            if pos < 0:
                self.buffer[:] = b"\xaa" if self.buffer[-1:] == b"\xaa" else b""
                break
            del self.buffer[:pos]
            if len(self.buffer) < 8:
                break
            version, kind, sequence, length = struct.unpack_from("<BBHH", self.buffer, 2)
            if version != 2 or length > 256:
                del self.buffer[0]
                continue
            total = 10 + length
            if len(self.buffer) < total:
                break
            data = bytes(self.buffer[:total])
            if crc16(data[2:-2]) != struct.unpack_from("<H", data, total - 2)[0]:
                del self.buffer[0]
                continue
            result.append((kind, sequence, data[8:-2]))
            del self.buffer[:total]
        return result


class V2Link:
    def __init__(self, port: str, baudrate=115200, timeout_ms=180, serial_factory=None):
        self.port, self.baudrate = port, baudrate
        self.timeout = timeout_ms / 1000
        self.factory = serial_factory
        self.serial = None
        self.decoder = Decoder()
        self.sequence = 0
        self.healthy = False
        self.telemetry = None
        self.last_ack_at = None

    def connect(self):
        self.close()
        if self.factory is None:
            import serial
            self.factory = serial.Serial
        self.serial = self.factory(self.port, self.baudrate, timeout=0.02, write_timeout=self.timeout)
        self.decoder = Decoder()
        self.healthy = True
        try:
            self.exchange(HELLO, expected=HELLO_ACK)
            self.exchange(STOP)
        except Exception:
            self.close()
            raise

    def exchange(self, kind: int, payload=b"", expected=ACK):
        if not self.serial or not self.healthy:
            raise RuntimeError("V2 link is unavailable; reconnect required")
        self.sequence = (self.sequence + 1) & 0xFFFF
        sequence = self.sequence
        wire = frame(kind, sequence, payload)
        try:
            if self.serial.write(wire) != len(wire):
                raise RuntimeError("Partial serial write")
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                for typ, seq, body in self.decoder.feed(self.serial.read(512)):
                    if typ == TELEMETRY and len(body) == 10:
                        left, right, battery, angle, obstacle = struct.unpack("<hhHHH", body)
                        self.telemetry = {"left_target": left, "right_target": right,
                                          "battery_raw": battery, "angle_raw": angle,
                                          "obstacle_raw": obstacle, "measured_wheel_speed": None}
                    if typ == FAULT:
                        raise RuntimeError("Firmware FAULT: " + body.hex())
                    if typ != expected or seq != sequence:
                        continue
                    if typ == ACK and body != struct.pack("<H", sequence):
                        continue
                    if typ == HELLO_ACK and body != b"\x02\x01":
                        raise RuntimeError("Unexpected V2 capabilities")
                    self.last_ack_at = time.monotonic()
                    return
            raise TimeoutError("No matching V2 response")
        except Exception:
            self.healthy = False
            raise

    def set_targets(self, left: int, right: int, duration_ms: int):
        if not 1 <= duration_ms <= 500:
            raise ValueError("Motion requires a 1..500 ms deadline")
        payload = struct.pack("<hhHB", max(-1000, min(1000, left)),
                              max(-1000, min(1000, right)), duration_ms, 0)
        self.exchange(SET_MOTOR, payload)

    def close(self):
        if self.serial:
            self.serial.close()
        self.serial = None
        self.healthy = False
