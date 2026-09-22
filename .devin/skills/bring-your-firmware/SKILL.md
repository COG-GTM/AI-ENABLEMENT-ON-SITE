---
name: bring-your-firmware
description: Point the workflows at your own C/C++ firmware tree - map the build and HAL boundary, stand up a host-side test harness with stubbed hardware (templates/host-harness), get the first tests running on a laptop, then chain into /tdd, /design-artifacts, /track-and-report, and /exec-deck.
argument-hint: "[path to firmware tree] [--framework googletest|unity|ceedling|none] [--harness-dir path]"
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

Bring firmware into the workflow: `$ARGUMENTS`.

## Goal

After this skill the engineer has, on a laptop with no board attached: their own firmware modules compiled
with a host compiler, hardware replaced by a scripted stub, a handful of behaviour tests that pass, and a
written list of what only the target build can prove. Everything else in this repository (`/tdd`,
`/design-artifacts`, `/what-if-part-swap`, `/track-and-report`, `/exec-deck`) then works on their code
the same way it works on `example-system/`.

Read-only until step 3. Never modify the customer's build files; add a harness beside the tree.

## Step 1 - Map the tree (read, do not change)

Report these in `outputs/<tree>-firmware-map.md`, each with the file that proves it:

| Question | Where to look | Why it matters |
| --- | --- | --- |
| Build system and toolchain | `Makefile`, `CMakeLists.txt`, `*.ewp`, `*.uvprojx`, `.cproject`, `Kconfig`, `west.yml`; `CC=`, `arm-none-eabi-`, `iccarm`, `armclang` | Which files are portable C vs toolchain-bound |
| Target, RTOS, vendor SDK | startup files, linker scripts (`.ld`, `.icf`), `FreeRTOSConfig.h`, `zephyr/`, `CMSIS/`, `HAL_Driver/`, `sdk/` | These stay out of the host build |
| HAL / driver boundary | functions that touch registers, `HAL_SPI_*`, `nrf_*`, `spi_transceive`, DMA, ISRs, `volatile` | The line the stub replaces |
| Pure logic | filters, protocol encode/decode, state machines, budgets, CRC, scheduling decisions | What the host tests cover |
| Existing tests and framework | `test/`, `tests/`, `unity.h`, `gtest/gtest.h`, `ceedling`, `CppUTest`, `project.yml` | Reuse it; do not add a second framework |
| Existing standards | `.clang-format`, `misra*`, `cppcheck` config, coverage flags, coding-standard doc | Match them; note them as target-side gates |
| Requirement and hazard IDs | comments like `REQ-`, `SRS-`, `HAZ-`, DOORS exports, `docs/` | Feed `/design-artifacts` and the traceability matrix |

Ask one question at a time when the map has a hole: "Which of these files do you build for the target
but would be fine to compile on a PC?" is usually the right first question.

## Step 2 - Choose the seam

Two ways to swap hardware out. Pick by what the tree already does.

| Firmware style | Seam | Harness pattern |
| --- | --- | --- |
| Logic calls HAL functions directly (`hal_spi_transfer(...)`, `HAL_I2C_Mem_Read(...)`) | **Link-time**: compile logic with `hal_stub.c` instead of the vendor driver; declare the same prototypes in `hal_stub.h` | `templates/host-harness/hal_stub.c` and `hal_stub.h` renamed to match their prototypes |
| Logic takes function pointers / a struct of callbacks (`node_init(..., read_imu, ...)`) | **Callback**: pass adapters that read from the stub | `templates/host-harness/test_main.c` section 2 |
| Logic is tangled with registers and ISRs | Neither yet | First extract a pure function (one `static` at a time) with `/tdd`; report the coupling as a finding |

If they have a framework, keep it: the stub is framework-neutral C; only `harness.h` (the `CHECK` macros)
is replaced by GoogleTest / Unity / CppUTest assertions.

## Step 3 - Build the harness

Copy `templates/host-harness/` next to their tree (`host-tests/` is a fine name), then:

1. `Makefile`: set `FW_SRC` to the portable `.c` files from step 1, `FW_INC` to their include dirs. Keep
   `-Wall -Wextra -Werror`; if their code does not build clean on a host compiler, that is finding #1, not
   a reason to drop the flags. C++ trees: `CXX`, `-std=c++17`, same idea.
2. `hal_stub.h`: rename the six HAL functions to their prototypes. Keep the control API
   (`hal_stub_script_*`, `hal_stub_fail_*`, `hal_stub_spi_default`, `hal_stub_advance_ms`, `hal_stub_log`).
3. `test_main.c`: keep section 1 (stub self-test) as-is; replace section 2 adapters and section 3 tests.

The stub is deterministic and bounded: scripted bytes per device, a repeating default SPI frame for long
polling loops, failure injection by count, a recorded UART/GPIO log, and a millisecond clock that only
moves when a test moves it. No threads, no sleeps, no real time.

```bash
make -C templates/host-harness test                      # the proof: runs against example-system/src
make -C host-tests test FW_SRC="src/filter.c src/proto.c" FW_INC=include   # their tree
```

## Step 4 - First three tests

Always the same three, because they show the shape without knowing the domain:

1. **Nominal**: scripted sensor data in, one correct output frame out, clock advanced by the expected period.
2. **Fault**: inject a bus failure; assert the firmware's fault flag, retry, or re-init path fired (count
   the GPIO/bus calls in `hal_stub_log`).
3. **Boundary**: an extreme value the protocol must carry (type limits, counter wrap, empty buffer).

Name tests after behaviour and requirement ID (`test_five_missed_imu_samples_set_fault /* SN-REQ-008 */`).
Then hand off to `/tdd` for the next behaviour.

## Step 5 - Say what the host build does not prove

Put this list, filled in for their tree, at the end of the firmware map. Host tests cover logic; they do not
cover: cross-compiler behaviour (packing, alignment, `int` width, intrinsics), interrupt latency and timing,
RTOS scheduling, peripheral silicon behaviour, DMA, power modes, or link-map/memory fit. They are also **not**
evidence for MISRA C, DO-178C objectives, FACE conformance, or any certification artefact; those need the
project's own static analysis, coverage, and target testing. The host harness makes those gates cheaper by
catching logic defects first; it does not replace them.

## Chain

`/bring-your-firmware ../their-tree` → `/tdd` (next behaviour) → `/design-artifacts` (requirements,
hazards, ICD from what the tests exposed) → `/track-and-report` (findings become tracker items) →
`/exec-deck` (what was found, what is proven, what needs the lab). Pipeline: `WORKFLOWS.md`.

## Worked example

`/bring-your-firmware example-system/src`
Map: `Makefile`, host `cc`, no RTOS, callback HAL (`node_init(..., imu_fn, reinit_fn, temp_fn, ctx)`), pure
`filter.c`/`packet.c`/`node.c`, requirement IDs `SN-REQ-*` in comments. Seam: callback. Harness: as shipped
in `templates/host-harness/`. Tests: one second → one valid packet; five SPI failures → IMU reset on GPIO 7
and `FLAG_IMU_REINIT`; I2C NAK → `FLAG_FAULT` with last good temperature. 58 checks pass on a laptop.
