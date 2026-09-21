"""Print a few packets from a simulated node.  Run: python -m sim.sensor_node.demo"""

import math

from .node import SensorNode
from .packet import parse_packet


def main(seconds: int = 5) -> None:
    t = [0]

    def imu():
        t[0] += 1
        # Slow tilt on X, gravity on Z (8192 LSB/g), tiny gyro noise.
        return (int(400 * math.sin(t[0] / 50)), 0, 8192, (t[0] % 7) - 3)

    node = SensorNode(read_imu=imu, read_temp=lambda: 2350 + (t[0] % 3))
    for _ in range(seconds * 100):
        pkt = node.step()
        if pkt:
            p = parse_packet(pkt)
            print(f"seq={p.seq:5d} acc=({p.acc_x:6d},{p.acc_y:6d},{p.acc_z:6d}) "
                  f"gyro_z={p.gyro_z:4d} temp={p.temp_cc / 100:.2f}C flags=0x{p.flags:02x}  {pkt.hex()}")


if __name__ == "__main__":
    main()
