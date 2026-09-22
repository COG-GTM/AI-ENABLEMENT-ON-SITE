# Plan: Diagnostics packet

Spec: `spec.md` (must be approved before this plan is executed)

## Approach

Add a second packet type that reuses the existing 16-byte frame, CRC rule, and sequence counter, so
the host decoder changes by one `if SYNC == 0xA6` branch and no data-packet test moves. The node
counts data packets and emits the diagnostics frame in place of nothing (extra frame, not a replaced
one) every 60th second. Both twins change in lockstep; a shared golden vector proves they agree.

## Affected files

| File | Change |
| --- | --- |
| `example-system/docs/ICD.md` | modify: section 4 gains "4b. Diagnostics packet (SYNC 0xA6)" table |
| `example-system/docs/SRS.md` | add: SN-REQ-011 "one diagnostics packet per 60 data packets" |
| `example-system/src/packet.h`, `packet.c` | add: `SYNC_DIAG`, `packet_build_diag()`; parse accepts both SYNC values |
| `example-system/sim/sensor_node/packet.py` | add: same API as the C twin |
| `example-system/src/node.h`, `node.c` | modify: data-packet counter, uptime seconds, emit diag frame |
| `example-system/sim/sensor_node/node.py` | modify: same |
| `example-system/tests/test_packet.py`, `test_firmware.c` | add: golden vector for one diag frame, mixed-stream parse |
| `example-system/tests/test_node.py`, `test_firmware.c` | add: 60-packet cadence, reinit count carried |
| `example-system/tracker.json` | modify: SN-BUG-004 -> closed, SN-CAP-005 -> in_review when merged |

## Data and interface changes

- Packet / message / API fields added or changed (reference ICD section 4b):
  `0 SYNC=0xA6, 1 FLAGS, 2-3 SEQ, 4-5 REINIT u16, 6-9 UPTIME_S u32, 10-11 VBAT_MV u16 (reserved 0), 12-13 reserved 0, 14-15 CRC`.
- Config or schema changes: none. Tracker schema unchanged.

## Test strategy

- Existing tests expected to break and why: none. `test_packet` fixtures use SYNC 0xA5 and are untouched; the
  parser accepts 0xA5 and 0xA6 and rejects everything else as before.
- New tests (name, what they prove):
  - `test_diag_golden_vector` (both twins): the same inputs give the same 16 bytes and CRC.
  - `test_diag_every_60_packets` (both twins): 61 data packets in, exactly one diag frame out, then data resumes.
  - `test_diag_carries_reinit_count` (both twins): two forced IMU timeouts -> REINIT field 2.
  - `test_mixed_stream_parses` (Python): interleaved 0xA5/0xA6 frames all parse; a 0xA7 frame is rejected.
- Both twins (Python and C) updated: yes.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Host decoder in the field treats 0xA6 as corrupt and drops it | medium | Frame is dropped, not misparsed (SYNC check first); document in ICD change log |
| Counter and uptime add a few bytes of RAM | low | Two `uint32_t`; no allocation (SN-REQ-023) |
| Diag frame lands in the same 10 ms slot as a data frame and pushes timing past 8 ms | low | `test_timing` extended to the diag path; TIMING.md gets a row |

## Rollback

Set `DIAG_INTERVAL` to 0 in both twins (compile-time constant) and the node never emits 0xA6; host code
already ignores unknown SYNC. No ICD rollback needed because 0xA6 stays documented as optional.
