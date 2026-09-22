# Software requirements specification: sensor node firmware

Synthetic example. IDs are stable; skills and tests reference them.

## 1. Scope

The sensor node samples an inertial measurement unit (IMU) and a temperature sensor, filters the
readings, and sends fixed-format packets over a UART uplink. It runs from a 2000 mAh battery.

## 2. Functional requirements

| ID | Requirement | Priority | Verified by |
| --- | --- | --- | --- |
| SN-REQ-001 | The node shall sample the IMU at 100 Hz (+/- 1 %). | Must | TIMING.md, `test_timing` |
| SN-REQ-002 | The node shall sample temperature at 1 Hz. | Must | `test_timing` |
| SN-REQ-003 | The node shall apply a 4-sample moving-average filter to each IMU axis before transmission. | Must | `test_filter` |
| SN-REQ-004 | The node shall transmit one uplink packet per second containing the latest filtered IMU sample, temperature, sequence number, and CRC-16. | Must | `test_packet` |
| SN-REQ-005 | Packets shall be exactly 16 bytes as defined in ICD section 4. | Must | `test_packet` |
| SN-REQ-006 | The CRC-16/CCITT-FALSE over bytes 0-13 shall be placed in bytes 14-15, big-endian. | Must | `test_packet` |
| SN-REQ-007 | A temperature reading outside -40 to +85 C shall set the FAULT flag and keep the last valid value. | Must | `test_temp_fault`, SN-HAZ-002 |
| SN-REQ-008 | If the IMU fails to respond for 5 consecutive samples, the node shall set the FAULT flag and reinitialise the IMU. | Must | `test_imu_timeout`, SN-HAZ-001 |
| SN-REQ-009 | The sequence number shall wrap from 65535 to 0 without error. | Should | `test_packet` |
| SN-REQ-010 | The node shall enter low-power sleep between samples. | Should | POWER-BUDGET.md |

## 3. Non-functional requirements

| ID | Requirement | Priority | Verified by |
| --- | --- | --- | --- |
| SN-REQ-020 | Average current shall not exceed 2.7 mA so that the 2000 mAh battery lasts 30 days. | Must | POWER-BUDGET.md |
| SN-REQ-021 | Worst-case loop execution time shall not exceed 8 ms (80 % of the 10 ms period). | Must | TIMING.md |
| SN-REQ-022 | Firmware shall build with `-Wall -Wextra -Werror` and pass all tests on the host. | Must | `make test` |
| SN-REQ-023 | No dynamic memory allocation after initialisation. | Must | code review |

## 4. Traceability

Hazards: `HAZARDS.md` maps SN-HAZ-001..004 to SN-REQ-007, 008, 020.
Decisions: `ADR-0001.md` (moving average vs IIR), `ADR-0002.md` (UART vs CAN uplink).
Open items: see `../tracker.json`.
