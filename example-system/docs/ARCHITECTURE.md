# Architecture overview: sensor node

Synthetic example, arc42-style but short. Regenerate with `/architecture-doc` after code changes.

## 1. Purpose and constraints

Sample motion and temperature, filter, and send one 16-byte packet per second over UART from a
2000 mAh battery for 30 days. Constraints: no FPU, no heap after init (SN-REQ-023), host-testable.

## 2. Context

```
 [IMU] --SPI--> [Sensor node MCU] --UART 115200--> [Host / gateway]
 [Temp] --I2C--/
```

## 3. Building blocks

| Module | C | Python twin | Responsibility |
| --- | --- | --- | --- |
| filter | `src/filter.c` | `sim/sensor_node/filter.py` | 4-sample moving average per axis (ADR-0001) |
| packet | `src/packet.c` | `sim/sensor_node/packet.py` | Build/parse 16-byte packet, CRC-16 (ICD section 4) |
| node | `src/node.c` | `sim/sensor_node/node.py` | 10 ms tick: sample, filter, fault handling, 1 Hz emit |
| hardware | function pointers in `node.h` | callables in `node.py` | IMU/temperature access injected by the board layer or tests |

## 4. Runtime view (one 10 ms tick)

```
tick -> read_imu -> [miss? count; 5 misses => FAULT + reinit] -> filter x4
     -> every 100th tick: read_temp -> [range check => FAULT]
     -> every 100th tick: build packet(seq, filtered, temp, flags) -> uplink; clear flags
```

## 5. Key decisions

- ADR-0001 moving average over IIR.
- ADR-0002 UART now, CAN-compatible packet format.

## 6. Quality scenarios

| Scenario | Requirement | Evidence |
| --- | --- | --- |
| IMU unplugged mid-run | SN-REQ-008 | fault tests in `tests/` |
| Corrupted byte on the wire | SN-REQ-006 | `test_corruption_detected` |
| 30-day battery life | SN-REQ-020 | `POWER-BUDGET.md` (currently 28.1 days, SN-BUG-003 open) |

## 7. Risks and technical debt

See `HAZARDS.md` (SN-HAZ-004 open) and `../tracker.json`.
