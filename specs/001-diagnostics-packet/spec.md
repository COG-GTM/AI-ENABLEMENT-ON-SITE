# Spec: Diagnostics packet

Status: reviewed
Requirement IDs touched: SN-REQ-004, SN-REQ-005, SN-REQ-008, new SN-REQ-011
Tracker: SN-BUG-004, SN-CAP-005. Hazards: SN-HAZ-001, SN-HAZ-004.

## Problem

The node reinitialises the IMU after five missed samples (SN-REQ-008) and counts it in
`imu_reinit_count`, but no packet field carries that count, so the host cannot tell one glitch from a
failing sensor (SN-BUG-004). The host also has no uptime or battery figure to correlate with the power
budget (SN-HAZ-004).

## Users

- Field technician needs the reinit count and uptime on the host so that a flaky IMU is found before it fails.
- Power engineer needs a battery-voltage reading so that the 30-day claim (SN-REQ-020) can be checked in the field.

## User stories and acceptance criteria

### US-1: Periodic diagnostics packet

Given the node is running
When 60 data packets have been sent
Then the node sends one diagnostics packet (SYNC 0xA6, 16 bytes, same CRC rule) and then resumes data packets.

### US-2: Reinit count is visible

Given the IMU has timed out twice since boot
When the next diagnostics packet is parsed on the host
Then its REINIT field is 2 and its FLAGS still carries IMU_REINIT if a reinit happened in this window.

### US-3: Data packets are unchanged

Given an existing host decoder built for the 0xA5 data packet
When it receives a mixed stream of data and diagnostics packets
Then every 0xA5 packet parses exactly as before and every 0xA6 packet is recognised by SYNC, not guessed.

## Non-goals

- Changing the data packet layout or rate (SN-REQ-004, SN-REQ-005 stay as they are).
- Battery voltage on the current board (no ADC path in the ICD; field is reserved and reads 0).
- Any host-side dashboard.

## Constraints

- Memory / flash: no dynamic allocation (SN-REQ-023); one extra 16-byte buffer at most.
- Timing: building the diagnostics packet must fit inside the existing 8 ms worst-case loop (SN-REQ-021).
- Power: one extra 16-byte UART frame per minute, below 0.001 mA average; POWER-BUDGET.md unchanged.
- Interfaces (ICD sections affected): section 4 gains a second packet type; section 3 unchanged.
- Security / safety (hazard IDs): SN-HAZ-001 (undetected IMU failure) gets a detection path; SN-HAZ-003 unaffected because the CRC rule is shared.

## Open questions

- [NEEDS CLARIFICATION] Interval: every 60 data packets (1/min) or every 10? Default to 60 unless the host team objects.
- [NEEDS CLARIFICATION] Should uptime be seconds since boot (u32, wraps at 136 years) or packets sent (u32)? Default: seconds.
