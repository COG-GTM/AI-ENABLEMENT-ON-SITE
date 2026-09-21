# Power budget: sensor node

Synthetic numbers. Battery 2000 mAh, target 30 days => average current limit
2000 mAh / 720 h = 2.78 mA. Requirement SN-REQ-020 sets 2.7 mA with margin.

Part numbers refer to `../parts/*.json`; the what-if skill recomputes this table from those files.

| Consumer | Part | Active current | Duty cycle | Average |
| --- | --- | --- | --- | --- |
| MCU active (32 MHz) | mcu-m0 | 6.0 mA | 40 % (4 ms of each 10 ms) | 2.40 mA |
| MCU sleep | mcu-m0 | 0.010 mA | 60 % | 0.006 mA |
| IMU, 100 Hz ODR | imu-a | 0.55 mA | 100 % | 0.55 mA |
| Temperature sensor | temp-x | 0.20 mA conv / 0.001 mA idle | 3 % (30 ms of 1 s) | 0.007 mA |
| UART transmit | mcu-m0 | 2.0 mA | 0.14 % (16 bytes at 115200 = 1.4 ms/s) | 0.003 mA |
| **Total** | | | | **2.97 mA** |

## Status

Total 2.97 mA exceeds the 2.7 mA limit by 10 %. Estimated life: 2000 / 2.97 = 673 h = 28.1 days.

Root cause: MCU duty cycle. The loop currently busy-waits instead of sleeping (SN-BUG-003, SN-HAZ-004).
With sleep implemented, MCU active duty drops to about 25 % => MCU average 1.50 mA, total 2.07 mA,
life 40 days. This is the highest-value open item on the tracker.

## Method

average = active_current x duty_cycle; life_hours = capacity_mAh / total_mA; life_days = life_hours / 24.
The same formulas are implemented in `tools/what_if.py` so numbers are recomputed, not hand-copied.
