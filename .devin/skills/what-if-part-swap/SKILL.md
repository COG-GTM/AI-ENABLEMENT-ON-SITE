---
name: what-if-part-swap
description: Analyse the impact of swapping or adding a chip, sensor, or device (power, timing, interface, ICD, firmware, hazards) and recommend go / no-go.
argument-hint: "[current-part] -> [candidate-part] | add [part]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

What-if analysis for a hardware change. Request: `$ARGUMENTS`.
Available synthetic parts: `example-system/parts/*.json` (`imu-a` current, `imu-b`, `imu-c`, `can-xcvr`, ...).
If the user names a real part, ask them to add a JSON file in the same shape with data-sheet values;
never guess a real part's numbers.

## Steps

1. Identify the change: replacement (`X -> Y`) or addition (`add Z`). Restate what must stay true
   (requirements affected, from `example-system/docs/SRS.md`).
2. Recompute budgets:
   ```
   python tools/what_if.py                              # baseline
   python tools/what_if.py --imu imu-b --markdown       # candidate (also: --uplink can-xcvr, --mcu-duty 0.25)
   ```
   The tool prints the power table, PASS/FAIL against SN-REQ-020, life in days, and compatibility issues.
3. Walk the impact checklist and write one line each:
   - Electrical: supply range, extra rails, package/footprint.
   - Interface: bus type, speed, address collisions, pin count (ICD sections 1-3).
   - Data: scale factors, register map, WHO_AM_I, burst size (ICD section 4 units; firmware drivers).
   - Timing: bytes per read, conversion time (`docs/TIMING.md`).
   - Power: from step 2.
   - Firmware: which of `src/*.c` and `sim/sensor_node/*.py` change; which tests need new golden values.
   - Safety: which hazards change likelihood (`docs/HAZARDS.md`), any new failure mode.
   - Schedule/risk: qualification, second source, obsolescence (mark as assumed if unknown).
4. Write `outputs/what-if-<slug>.md`: summary verdict (go / no-go / go with conditions), the table from
   step 2, the checklist, and the list of documents that would need an update (ICD, ADR, SRS, tests).
5. If the user says go: draft the ADR with `/design-artifacts adr`, and add a capability item with
   `/track-and-report`. Do not change firmware unless asked.

## Example verdicts

- `imu-a -> imu-b`: go with conditions (WHO_AM_I change, 12-byte burst, retest); power improves to PASS
  once sleep mode lands.
- `imu-a -> imu-c`: no-go for this board (I2C only, different scale factors, +0.65 mA, 5 % over timing row).
- `add can-xcvr`: no-go without a 5 V rail; see ADR-0002.
