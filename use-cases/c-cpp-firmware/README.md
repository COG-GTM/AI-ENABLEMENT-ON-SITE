# Use case: a C/C++ firmware repository, from target boundaries to a proven behavioural twin

## Why

Firmware trees mix three kinds of code: logic that runs anywhere (parsers, filters, checksums, state machines),
code that only makes sense on the target (ISRs, memory-mapped registers, startup, linker sections), and vendor or
HAL code you did not write. Before anyone modernises, tests, or ports anything, the team needs to know which is
which, where the HAL seam is, and what depends on what. This lane finds that from the source, stands up a host
harness on the seam, and, where a Python model is wanted, builds a **behavioural twin** proven against the C.

**This repository does not translate C to Python.** The twin (`example-system/sim/`) is a reference model kept in
lock-step with the C (`example-system/src/`) by running the same tests and vectors against both. That is a
deliberate scope: it gives an executable specification and a host-side oracle without pretending a translator exists.

## When

- A C/C++ tree with no host build, no tests, or no map of what is target-only.
- You want to modernise or port module by module and prove each step on a laptop.
- You need a reference model (Python) that provably matches the firmware.

## What you need

- This repository, Python 3.10+, Devin Desktop, a host C compiler (`gcc` or `clang`) and `make`. No target hardware.
- Read-only access to the tree. `gcc` is also used for the include-graph cross-check; without it the scanner says so.

## Step by step (fixture shown; substitute your tree)

| # | Do | Leaves behind |
| --- | --- | --- |
| 1 | `/repo-discovery example-system/firmware-repo --lang c --name firmware-repo` (or `python tools/c_fleet_scan.py example-system/firmware-repo --name firmware-repo`; add `--cflags "-DBOARD_REV_C"` when headers need target flags) | `outputs/firmware-repo-c-fleet-inventory.csv`, `-c-fleet-summary.json`, `-c-repo-map.md`, `-c-dependency-map.json` + `.dot`, `-c-migration-backlog.json` + `.csv` |
| 2 | Read `outputs/firmware-repo-c-repo-map.md`: entry points, target-only files with the marker that made them so, seam candidates, vendor code, include and call trees, leaf-first order | where the host/target boundary is |
| 3 | `/bring-your-firmware example-system/firmware-repo` with the seam candidates from step 2 | `outputs/<tree>-firmware-map.md`, a `host-tests/` folder from `templates/host-harness/` with stubs on the seam |
| 4 | `python tools/prompt_pack.py --map outputs/firmware-repo-c-dependency-map.json` | `outputs/packs/firmware-repo-c/<ID>.md`, `manifest.json` |
| 5 | For the first leaf-first `port` unit: `/tdd Host-test <unit> against the harness; then write the Python twin, tests first, exact match on the vectors` | tests + code, `make test` green, `outputs/<unit>-compare.md` |
| 6 | `/track-and-report status of outputs/firmware-repo-c-migration-backlog.json`; `/exec-deck Migration readiness from outputs/firmware-repo-c-fleet-summary.json` | tracker report, deck |

Unattended: `python tools/pipeline_run.py --lang c --tree example-system/firmware-repo --name firmware-repo`.

## What the fixture shows (numbers from `outputs/golden/REPORT.md`)

`example-system/firmware-repo/`: 30 synthetic files: an ISR (`ADC_IRQHandler`), memory-mapped registers and
`volatile` state, a linker script and section attributes, `#if` board variants with `#error` for unknown boards,
function-pointer command dispatch, C++ classes, templates and overloads, a HAL boundary (`drivers/hal_gpio.c`),
vendor code (`third_party/crc16_vendor.c`), a K&R-style legacy file, a non-UTF-8 file, host tests and vectors,
a cross-compiler `Makefile`.

- 30 parsed (16 sources, 14 headers, 5 C++), 0 unreadable; 47 functions, 1 test file, 2 build files
- 32 include edges, 11 call edges, 1 unresolved call, 4 indirect (function-pointer / method) calls, 6 vendor calls, 0 cycles
- classification: port 21, wrap 4, retain 5; 2 seam candidates (`hal_gpio_write`, `crc16_vendor`); 15 backlog items
- include reader: `gcc -MM` cross-check when gcc is present; `gcc disabled (--no-gcc)` otherwise
- `python tools/c_fleet_scan.py --check` compares a fresh scan with `expected/`
- Finished twin: `example-system/src` (C) and `sim/` (Python) pass the same 57 tests; the MATLAB vector run matches
  both exactly; `templates/host-harness` runs 58 checks against the C through `hal_stub.c`

## How the scanner works

`tools/c_fleet_scan.py` tokenises each file (standard library only), finds function definitions (C and C++, K&R,
methods, constructors), macros, includes, and candidate calls, resolves includes inside the tree, and marks files
`retain` when they carry ISR, inline assembly, register, linker, or startup markers; `wrap` when they are vendor or
include target-only headers; `port` otherwise. A seam candidate is a function in a retain/wrap file that host-side
code calls: the place to put a stub. When `gcc` is present, `gcc -MM` cross-checks the include graph and reports
the preprocessor's errors (for the fixture without board flags: `error: #error "unknown board"`).

## What this does not prove

- Macros are not expanded, `#if` branches are not evaluated, function pointers are not followed, C++ overloads,
  templates, and virtual dispatch are matched by name only. Edges are candidate evidence.
- Host tests prove logic on a laptop, not timing, interrupt behaviour, or anything on the target.
- There is no C-to-Python translator. A Python twin is written test-first and proven on shared vectors; if
  translation is the requirement, that is a gap to state, not a feature to imply.

## Skills and files

`.devin/skills/repo-discovery/SKILL.md`, `.devin/skills/bring-your-firmware/SKILL.md`, `.devin/skills/tdd/SKILL.md`,
`tools/c_fleet_scan.py`, `tools/prompt_pack.py`, `templates/host-harness/`, `example-system/firmware-repo/`,
`example-system/src/`, `example-system/sim/`, `WORKFLOWS.md` sections 8 and 11.
