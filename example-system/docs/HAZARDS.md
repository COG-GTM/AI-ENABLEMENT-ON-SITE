# Hazard analysis (FMEA style): sensor node

Synthetic example. Severity 1 (negligible) to 4 (critical); Likelihood 1 (remote) to 4 (frequent);
Risk = Severity x Likelihood. Anything >= 8 needs a mitigation traced to a requirement.

| ID | Failure mode | Effect | Sev | Lik | Risk | Mitigation | Verified by | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SN-HAZ-001 | IMU stops responding on SPI (wiring, brown-out, latch-up) | Stale motion data reported as fresh | 3 | 3 | 9 | Detect 5 missed samples, set FAULT, reinitialise IMU (SN-REQ-008) | `test_node.test_imu_timeout_triggers_reinit`, C `test_imu_timeout` | Mitigated |
| SN-HAZ-002 | Temperature sensor returns out-of-range value (bus glitch) | Wrong temperature used downstream | 2 | 3 | 6 | Range check, keep last valid value, set FAULT (SN-REQ-007) | `test_node.test_out_of_range_temp...`, C `test_temp_fault` | Mitigated |
| SN-HAZ-003 | Bit error on UART uplink | Corrupted packet accepted by host | 3 | 2 | 6 | CRC-16 over payload (SN-REQ-006) | `test_packet.test_corruption_detected` | Mitigated |
| SN-HAZ-004 | Battery depletes early (higher duty than budgeted) | Loss of telemetry before scheduled swap | 3 | 2 | 6 | Power budget with 15 % margin (SN-REQ-020), sleep between samples (SN-REQ-010) | `POWER-BUDGET.md` review | Open: sleep not yet implemented, see SN-BUG-003 |
| SN-HAZ-005 | Loop overruns 10 ms period under worst case | Missed IMU samples, filter distortion | 2 | 2 | 4 | Timing budget (SN-REQ-021) | `TIMING.md` | Accepted |
| SN-HAZ-006 | Sequence counter wrap mishandled by host | Host drops or reorders packets | 1 | 2 | 2 | Explicit wrap behaviour (SN-REQ-009) | `test_packet.test_seq_wraps` | Mitigated |

## Notes for reviewers

- Sev/Lik values are illustrative; they exist so that ranking, sorting, and "top risks" slides have real numbers.
- SN-HAZ-004 is the only hazard with an open mitigation; `tracker.json` carries it as SN-BUG-003.
