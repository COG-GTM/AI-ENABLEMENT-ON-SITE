"""Uplink packet encode/decode (ICD section 4, SN-REQ-004..006, 009). Mirrors src/packet.c."""

import struct
from dataclasses import dataclass

SYNC = 0xA5
PACKET_LEN = 16
FLAG_FAULT = 0x01
FLAG_IMU_REINIT = 0x02

_HEADER = struct.Struct(">BBHhhhhh")  # sync, flags, seq, acc_x, acc_y, acc_z, gyro_z, temp_cc


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Packet:
    seq: int
    acc_x: int
    acc_y: int
    acc_z: int
    gyro_z: int
    temp_cc: int
    flags: int = 0

    @property
    def fault(self) -> bool:
        return bool(self.flags & FLAG_FAULT)


def build_packet(p: Packet) -> bytes:
    if not 0 <= p.seq <= 0xFFFF:
        raise ValueError("seq out of range")
    if p.flags & ~0x03:
        raise ValueError("reserved flag bits must be zero")
    body = _HEADER.pack(SYNC, p.flags, p.seq, p.acc_x, p.acc_y, p.acc_z, p.gyro_z, p.temp_cc)
    return body + struct.pack(">H", crc16_ccitt_false(body))


def parse_packet(raw: bytes) -> Packet:
    if len(raw) != PACKET_LEN:
        raise ValueError(f"packet must be {PACKET_LEN} bytes, got {len(raw)}")
    sync, flags, seq, ax, ay, az, gz, temp = _HEADER.unpack(raw[:14])
    if sync != SYNC:
        raise ValueError("bad sync byte")
    (crc,) = struct.unpack(">H", raw[14:])
    if crc != crc16_ccitt_false(raw[:14]):
        raise ValueError("crc mismatch")
    return Packet(seq=seq, acc_x=ax, acc_y=ay, acc_z=az, gyro_z=gz, temp_cc=temp, flags=flags)


def next_seq(seq: int) -> int:
    return (seq + 1) & 0xFFFF
