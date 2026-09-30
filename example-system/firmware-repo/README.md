# C/C++ firmware repository fixture

Offline sample input for `/repo-discovery` and `tools/c_fleet_scan.py`: a small synthetic sensor-hub firmware
tree (30 C/C++ files, a `Makefile`, a linker script; hand-written, never built here) shaped like a typical
Cortex-M project: startup code, board registers, drivers, an interrupt handler, a scheduler, telemetry framing,
fixed-point control algorithms, a C++ logging layer, vendor CRC code, and a legacy corner. The single-module
fixture the `/bring-your-firmware` and `/tdd` skills use is `../src/` (with its Python twin in `../sim/`); this
tree is for the *repository-scale* question: what is in here, what includes and calls what, what can compile on
a laptop today, where is the hardware seam, where do we start.

Every construct that makes C/C++ discovery hard on a real tree is present on purpose, so the scanner's output
shows how each one is reported rather than guessed:

| Construct | Where | What the scanner does |
| --- | --- | --- |
| Cross-directory includes (`#include "hal_gpio.h"` from `app/`) | `app/main.c`, `drivers/spi_driver.c` | resolves relative to the includer, then by unique basename; `include` edges, headers gain `callers` |
| Memory-mapped registers through macros | `include/board.h` (`REG32`, `GPIOA_ODR`, `SPI1_DR`) | `retain`: register access; files that include it become `wrap` ("includes target-only header") |
| Interrupt handler and `volatile` shared state | `drivers/adc_isr.c` (`ADC_IRQHandler`), `drivers/spi_driver.c` | ISR name pattern -> `retain`, entry point; `volatile` counted and flagged for host testing |
| Inline assembly | `app/main.c` (`__asm volatile("wfi")`), `bsp/startup.c` | `retain` |
| Startup code, linker symbols, section attributes | `bsp/startup.c` (`_sidata`, `_estack`, `__attribute__((section(".isr_vector")))`), `bsp/sensor_hub.ld` | `retain`; the linker script is listed under build files |
| Board/architecture conditionals with `#error` | `bsp/system_init.c` (`BOARD_REV_C` / `BOARD_REV_B`) | counted per file; the `gcc -MM` cross-check fails on it until `--cflags=-DBOARD_REV_C` is passed, which is the point |
| Vendor / CMSIS calls | `bsp/system_init.c` (`HAL_Init`, `NVIC_SetPriority`, `__enable_irq`) | `calls_vendor` by prefix, never `unresolved` |
| Function pointers | `app/scheduler.c` (`t->fn(t->ctx)`), `cpp/command_parser.cpp` | `indirect_calls`, reported not followed |
| `static inline` in a header | `algo/fixed_point.h` (`q16_mul`, `q16_clamp`) | resolves for any file whose include closure reaches the header |
| Third-party code | `third_party/crc16_vendor.c` | `role = vendor`, `wrap`: keep as a dependency, do not rewrite; seam candidate when host-side code calls it |
| C++ template, class, namespace, overloads, `std::` calls | `cpp/ring_buffer.hpp`, `cpp/logger.cpp`, `cpp/command_parser.cpp` | counted in `cpp_constructs`; `obj.method(` becomes a `method-name` edge by name only; overloads flagged |
| Function-pointer member call | `cpp/logger.cpp` (`sink_(...)`) | `unresolved`: a name the scanner cannot prove is a function |
| K&R-style definition and `#if 0` | `legacy/old_filter.c` | definition still found; disabled lines ignored and noted |
| Non-UTF-8 bytes | `legacy/garbled.c` | decoded with replacement, noted, still inventoried; reason says to confirm the encoding |
| Toolchain hints in the build file | `Makefile` (`arm-none-eabi-gcc`, `-mcpu=cortex-m4`, `-DBOARD_REV_C`) | quoted in the repo map so the host harness knows what the target build defines |
| Tests and vectors | `tests/test_scheduler.c`, `tests/vectors/pid_vectors.csv` | `role = test`, excluded from the backlog, counted as evidence; `pid.c` is the one unit with vectors and is first in the backlog |
| Orphans | `algo/pid.c`, `app/telemetry.c`, `cpp/*.cpp`, `legacy/*` | `orphans` in the dependency map: nothing in the tree calls them |

`expected/c-fleet.json` and `expected/c-fleet-inventory.csv` are what `python tools/c_fleet_scan.py --check`
compares against (static include walk only, so the result does not depend on whether `gcc` is installed).
After a deliberate change to the fixture or the scanner run `python tools/c_fleet_scan.py --check --write-expected`
once and review the diff.

What this fixture is not: it is not the C twin of the Python model (that is `../src/` + `../sim/`), it does not
build (`make` here would need an ARM toolchain), and scanning it proves nothing about behaviour. The host
harness in `templates/host-harness/` is how the `port` and `wrap` units get compiled and tested on a laptop.
