---
name: tdd
description: Test-driven development loop (red, green, refactor) for Python or C, including the firmware twins in example-system.
argument-hint: "[behaviour to add or bug to fix] [--lang py|c|both]"
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

TDD for: `$ARGUMENTS`.

## Loop

1. **Red.** Write one failing test that states the behaviour in its name. Run only that test. Show the
   failure to the user. If it passes already, the test is wrong or the feature exists; stop and say so.
2. **Green.** Write the smallest change that makes it pass. No extra features. Run the test again.
3. **Refactor.** Remove duplication, keep names honest. Run the whole suite.
4. Repeat with the next behaviour. One behaviour per cycle. Commit after each green suite.

## Where tests live in this repository

| Code | Tests | Run |
| --- | --- | --- |
| `example-system/sim/sensor_node/*.py` | `example-system/tests/test_*.py` | `cd example-system && python -m unittest tests.test_node -k <name>` |
| `example-system/src/*.c` | `example-system/tests/test_firmware.c` | `make -C example-system test-c` |
| `tools/*.py` | `tools/tests/test_tools.py` | `python -m unittest discover -s tools/tests` |

Firmware rule: a behaviour that exists in both twins gets a test in both (Python first, then C with
the same golden values). The C build uses `-Wall -Wextra -Werror`; warnings are failures.

## Test quality checklist

- Name says the behaviour: `test_five_missed_imu_samples_set_fault`, not `test_node2`.
- One assertion idea per test; arrange / act / assert visible.
- Use the injected fake hardware (`SensorNode(imu=..., temp=...)`, `node_init(..., imu_fn, temp_fn, ctx)`);
  never sleep or read real devices.
- Golden values are computed and pasted from a run you show, not typed from memory.
- Edge cases: boundaries (65535 wrap, -4000 / 8500 temperature), empty, first-sample warm-up.

## Worked example

`/tdd Latch the temperature FAULT flag until a valid reading returns --lang both`
Red: `test_temp_fault_stays_set_until_valid_reading` in `test_node.py` fails (flag clears after one packet).
Green: keep `fault_temp` until `TEMP_MIN_CC <= t <= TEMP_MAX_CC`. Then the C twin, then update SN-REQ-007
wording via `/design-artifacts srs` and close SN-BUG-005 via `/track-and-report`.
