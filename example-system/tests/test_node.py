"""SN-REQ-001, 002, 004, 007, 008 - control loop, timing, and fault handling."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sim"))

from sensor_node.node import IMU_TIMEOUT_SAMPLES, SensorNode  # noqa: E402
from sensor_node.packet import FLAG_FAULT, FLAG_IMU_REINIT, parse_packet  # noqa: E402


def steady_imu():
    return (0, 0, 8192, 0)


class TestTiming(unittest.TestCase):
    def test_one_packet_per_second(self):  # SN-REQ-001, SN-REQ-004
        node = SensorNode(read_imu=steady_imu, read_temp=lambda: 2500)
        packets = [p for _ in range(1000) if (p := node.step())]
        self.assertEqual(len(packets), 10)
        self.assertEqual([parse_packet(p).seq for p in packets], list(range(10)))

    def test_temperature_sampled_once_per_second(self):  # SN-REQ-002
        calls = []
        node = SensorNode(read_imu=steady_imu, read_temp=lambda: calls.append(1) or 2500)
        for _ in range(300):
            node.step()
        self.assertEqual(len(calls), 3)


class TestFaults(unittest.TestCase):
    def test_out_of_range_temp_sets_fault_and_keeps_last_valid(self):  # SN-REQ-007
        temps = iter([2500, 9000, 2600])
        node = SensorNode(read_imu=steady_imu, read_temp=lambda: next(temps))
        pkts = [p for _ in range(300) if (p := node.step())]
        p0, p1, p2 = (parse_packet(p) for p in pkts)
        self.assertEqual((p0.temp_cc, p0.flags), (2500, 0))
        self.assertEqual((p1.temp_cc, p1.flags & FLAG_FAULT), (2500, FLAG_FAULT))
        self.assertEqual((p2.temp_cc, p2.flags), (2600, 0))  # flag clears after one packet

    def test_imu_timeout_triggers_reinit(self):  # SN-REQ-008
        misses = [0]

        def flaky_imu():
            misses[0] += 1
            return None if misses[0] <= IMU_TIMEOUT_SAMPLES else steady_imu()

        node = SensorNode(read_imu=flaky_imu, read_temp=lambda: 2500)
        pkt = next(p for _ in range(100) if (p := node.step()))
        parsed = parse_packet(pkt)
        self.assertTrue(parsed.flags & FLAG_FAULT)
        self.assertTrue(parsed.flags & FLAG_IMU_REINIT)
        self.assertEqual(node.imu_reinit_count, 1)

    def test_fewer_misses_than_timeout_is_not_a_fault(self):
        misses = [0]

        def brief_glitch():
            misses[0] += 1
            return None if misses[0] <= IMU_TIMEOUT_SAMPLES - 1 else steady_imu()

        node = SensorNode(read_imu=brief_glitch, read_temp=lambda: 2500)
        pkt = next(p for _ in range(100) if (p := node.step()))
        self.assertEqual(parse_packet(pkt).flags, 0)


if __name__ == "__main__":
    unittest.main()
