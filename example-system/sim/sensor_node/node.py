"""Sensor-node control loop (SN-REQ-001..010). Mirrors src/node.c.

Hardware is abstracted behind callables so tests can inject faults:
    read_imu()   -> (acc_x, acc_y, acc_z, gyro_z) or None when the IMU does not respond
    read_temp()  -> temperature in centi-degrees C
    reinit_imu() -> optional; called once each time the IMU timeout trips (SN-REQ-008)
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from .filter import MovingAverage
from .packet import FLAG_FAULT, FLAG_IMU_REINIT, Packet, build_packet, next_seq

IMU_RATE_HZ = 100
TEMP_RATE_HZ = 1
UPLINK_RATE_HZ = 1
IMU_TIMEOUT_SAMPLES = 5
TEMP_MIN_CC = -4000
TEMP_MAX_CC = 8500

ImuReader = Callable[[], Optional[tuple[int, int, int, int]]]
TempReader = Callable[[], int]
ImuReinit = Callable[[], None]


@dataclass
class SensorNode:
    read_imu: ImuReader
    read_temp: TempReader
    reinit_imu: Optional[ImuReinit] = None
    filters: list[MovingAverage] = field(default_factory=lambda: [MovingAverage(4) for _ in range(4)])
    seq: int = 0
    tick: int = 0
    fault: bool = False
    imu_reinit: bool = False
    imu_misses: int = 0
    imu_reinit_count: int = 0
    last_temp_cc: int = 2500
    filtered: tuple[int, int, int, int] = (0, 0, 0, 0)

    def step(self) -> Optional[bytes]:
        """Run one 10 ms tick. Returns an uplink packet once per second, else None."""
        self._sample_imu()
        if self.tick % (IMU_RATE_HZ // TEMP_RATE_HZ) == 0:
            self._sample_temp()
        packet = None
        if (self.tick + 1) % (IMU_RATE_HZ // UPLINK_RATE_HZ) == 0:  # end of each 1 s window
            packet = self._emit()
        self.tick += 1
        return packet

    def _sample_imu(self) -> None:
        raw = self.read_imu()
        if raw is None:
            self.imu_misses += 1
            if self.imu_misses >= IMU_TIMEOUT_SAMPLES:  # SN-REQ-008
                self.fault = True
                self.imu_reinit = True
                self.imu_reinit_count += 1
                self.imu_misses = 0
                for f in self.filters:
                    f.reset()
                if self.reinit_imu is not None:
                    self.reinit_imu()
            return
        self.imu_misses = 0
        self.filtered = tuple(f.update(v) for f, v in zip(self.filters, raw))  # type: ignore[assignment]

    def _sample_temp(self) -> None:
        t = self.read_temp()
        if TEMP_MIN_CC <= t <= TEMP_MAX_CC:
            self.last_temp_cc = t
        else:  # SN-REQ-007
            self.fault = True

    def _emit(self) -> bytes:
        flags = (FLAG_FAULT if self.fault else 0) | (FLAG_IMU_REINIT if self.imu_reinit else 0)
        ax, ay, az, gz = self.filtered
        pkt = build_packet(Packet(self.seq, ax, ay, az, gz, self.last_temp_cc, flags))
        self.seq = next_seq(self.seq)
        self.fault = False
        self.imu_reinit = False
        return pkt
