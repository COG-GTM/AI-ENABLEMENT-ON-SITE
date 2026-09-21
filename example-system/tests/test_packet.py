"""SN-REQ-004, 005, 006, 009 - uplink packet format."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))

from sensor_node.packet import (  # noqa: E402
    PACKET_LEN,
    SYNC,
    Packet,
    build_packet,
    crc16_ccitt_false,
    next_seq,
    parse_packet,
)


class TestPacket(unittest.TestCase):
    def test_crc_check_value(self):
        # Standard check value for CRC-16/CCITT-FALSE over "123456789".
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_length_and_sync(self):  # SN-REQ-005
        raw = build_packet(Packet(1, 0, 0, 8192, 0, 2350))
        self.assertEqual(len(raw), PACKET_LEN)
        self.assertEqual(raw[0], SYNC)

    def test_known_vector(self):  # SN-REQ-006, authoritative vector referenced by ICD section 4
        raw = build_packet(Packet(seq=1, acc_x=0, acc_y=0, acc_z=8192, gyro_z=0, temp_cc=2350))
        self.assertEqual(raw.hex(), "a50000010000000020000000092e776a")

    def test_round_trip(self):  # SN-REQ-004
        p = Packet(seq=1234, acc_x=-100, acc_y=55, acc_z=8000, gyro_z=-3, temp_cc=-1250, flags=0x01)
        self.assertEqual(parse_packet(build_packet(p)), p)

    def test_corruption_detected(self):
        raw = bytearray(build_packet(Packet(1, 0, 0, 0, 0, 0)))
        raw[5] ^= 0x01
        with self.assertRaises(ValueError):
            parse_packet(bytes(raw))

    def test_seq_wraps(self):  # SN-REQ-009
        self.assertEqual(next_seq(65535), 0)
        parse_packet(build_packet(Packet(65535, 0, 0, 0, 0, 0)))

    def test_reserved_flags_rejected(self):
        with self.assertRaises(ValueError):
            build_packet(Packet(0, 0, 0, 0, 0, 0, flags=0x04))


if __name__ == "__main__":
    unittest.main()
