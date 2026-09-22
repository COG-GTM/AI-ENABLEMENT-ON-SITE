# Tasks: Diagnostics packet

Plan: `plan.md`. Tests come before code in every group; a task is done when its named test passes in both twins.

## T1 Documents (no code)

- [ ] T1.1 ICD.md: add section 4b "Diagnostics packet (SYNC 0xA6)" with the byte table from plan.md.
- [ ] T1.2 SRS.md: add SN-REQ-011 "one diagnostics packet per 60 data packets", verified by `test_diag_every_60_packets`.
- [ ] T1.3 HAZARDS.md: add SN-REQ-011 to the mitigation column of SN-HAZ-001.

## T2 Packet twin (tests first)

- [ ] T2.1 Add `test_diag_golden_vector` to `tests/test_packet.py` and `tests/test_firmware.c` (expected 16 bytes, fails red).
- [ ] T2.2 Add `test_mixed_stream_parses` to `tests/test_packet.py` (0xA5 + 0xA6 accepted, 0xA7 rejected).
- [ ] T2.3 Implement `packet_build_diag()` in `src/packet.c` and `sim/sensor_node/packet.py`; extend parse to accept `SYNC_DIAG`.
- [ ] T2.4 `make -C example-system test` green.

## T3 Node twin (tests first)

- [ ] T3.1 Add `test_diag_every_60_packets` to `tests/test_node.py` and `tests/test_firmware.c`.
- [ ] T3.2 Add `test_diag_carries_reinit_count` to both.
- [ ] T3.3 Implement the counter, uptime seconds, and diag emission in `src/node.c` and `sim/sensor_node/node.py`.
- [ ] T3.4 Extend `test_timing` with the diag path; add the TIMING.md row.
- [ ] T3.5 `make -C example-system test` green.

## T4 Close out

- [ ] T4.1 `python tools/trace_matrix.py` shows SN-REQ-011 tested and SN-HAZ-001 mitigated by two requirements.
- [ ] T4.2 tracker.json: SN-BUG-004 closed with the closing note, SN-CAP-005 in_review.
- [ ] T4.3 `python tools/check_repo.py` green; open the PR with this spec folder linked.
