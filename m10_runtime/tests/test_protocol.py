import struct
import time

import pytest

from m10_runtime.protocol import ACK, HELLO, HELLO_ACK, SET_MOTOR, STOP, Decoder, V2Link, frame


class FirmwareSerial:
    """In-memory peer with independently checked header, length and response seq."""
    def __init__(self, *args, **kwargs):
        self.rx = bytearray()
        self.commands = []
        self.drop = False
        self.closed = False
        self.wrong_ack = False

    def write(self, wire):
        assert wire[:2] == bytes([170, 85])
        version, kind, seq, size = struct.unpack_from("<BBHH", wire, 2)
        assert version == 2 and len(wire) == size + 10
        self.commands.append((kind, wire[8:-2]))
        if not self.drop:
            if self.wrong_ack:
                self.rx.extend(frame(ACK, seq, struct.pack("<H", (seq - 1) & 0xFFFF)))
            else:
                self.rx.extend(frame(HELLO_ACK if kind == HELLO else ACK, seq,
                                     b"\x02\x01" if kind == HELLO else struct.pack("<H", seq)))
        return len(wire)

    def read(self, count):
        data = bytes(self.rx[:3])
        del self.rx[:3]
        if not data:
            time.sleep(0.001)
        return data

    def close(self):
        self.closed = True


def connected_link():
    peer = FirmwareSerial()
    link = V2Link("unused", timeout_ms=15, serial_factory=lambda *a, **k: peer)
    link.connect()
    return link, peer


def test_golden_hello_and_fragmented_noise_recovery():
    assert frame(HELLO, 1).hex() == "aa55020101000000b559"
    decoder = Decoder()
    wire = b"noise\xaa" + frame(HELLO, 1) + frame(STOP, 9)
    received = []
    for byte in wire:
        received.extend(decoder.feed(bytes([byte])))
    assert received == [(HELLO, 1, b""), (STOP, 9, b"")]


def test_corrupt_crc_and_invalid_length_do_not_hide_following_frame():
    bad = bytearray(frame(STOP, 2))
    bad[-1] ^= 1
    oversized = b"\xaa\x55\x02\x10\x01\x00\x01\x01"
    assert Decoder().feed(bytes(bad) + oversized + frame(STOP, 3)) == [(STOP, 3, b"")]


def test_handshake_and_signed_targets_match_firmware_layout():
    link, peer = connected_link()
    assert [c[0] for c in peer.commands] == [HELLO, STOP]
    link.set_targets(-200, 300, 250)
    assert peer.commands[-1] == (SET_MOTOR, struct.pack("<hhHB", -200, 300, 250, 0))
    assert link.healthy


@pytest.mark.parametrize("duration", [0, -1, 501])
def test_unbounded_or_oversized_motion_is_rejected(duration):
    link, peer = connected_link()
    with pytest.raises(ValueError):
        link.set_targets(100, 100, duration)
    assert all(kind != SET_MOTOR for kind, _ in peer.commands)


@pytest.mark.parametrize("failure", ["drop", "wrong_ack"])
def test_missing_or_wrong_ack_invalidates_link(failure):
    link, peer = connected_link()
    setattr(peer, failure, True)
    with pytest.raises(TimeoutError):
        link.set_targets(200, 200, 250)
    assert not link.healthy
    with pytest.raises(RuntimeError):
        link.set_targets(200, 200, 250)


def test_failed_handshake_closes_serial():
    peer = FirmwareSerial()
    peer.drop = True
    link = V2Link("unused", timeout_ms=10, serial_factory=lambda *a, **k: peer)
    with pytest.raises(TimeoutError):
        link.connect()
    assert peer.closed and link.serial is None
