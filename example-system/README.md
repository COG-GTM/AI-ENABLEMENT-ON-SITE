# Example system: battery-powered sensor node

A small, fully synthetic embedded system that every skill in this repository can work on.
Nothing here describes a real product or program.

```
        +------------------------------------------------------------+
        |  Sensor node (MCU, 3.3 V, 32 MHz)                          |
        |                                                            |
        |   IMU (SPI, 1 MHz) ---> filter ---> packet ---> UART uplink |
        |   Temp sensor (I2C) --/                     (115200 8N1)   |
        |                                                            |
        |   Battery 2000 mAh  ->  target 30 days   (see POWER-BUDGET) |
        +------------------------------------------------------------+
```

| Folder / file | What it is | Used by skills |
| --- | --- | --- |
| `docs/SRS.md` | Requirements (SN-REQ-001 ...) | design-artifacts, spec-driven, architecture-doc, exec-deck |
| `docs/ICD.md` | Interface control document: pins, buses, packet format | design-artifacts, what-if-part-swap |
| `docs/ADR-0001.md`, `docs/ADR-0002.md` | Architecture decision records | design-artifacts, architecture-doc |
| `docs/HAZARDS.md` | Hazard analysis / FMEA table | design-artifacts, exec-deck |
| `docs/POWER-BUDGET.md`, `docs/TIMING.md` | Budgets the what-if analysis recomputes | what-if-part-swap |
| `parts/*.json` | Synthetic "datasheets" for the current and candidate parts | what-if-part-swap |
| `src/` | C firmware modules (host-buildable, no hardware needed) | tdd, architecture-doc |
| `sim/sensor_node/` | Python twin of `src/` (runs anywhere, no compiler) | tdd, what-if-part-swap |
| `tests/` | Python `unittest` suite + C tests via `make test` | tdd |
| `tracker.json` | Bugs, defects, and capabilities for this system | track-and-report, exec-deck |
| `bench/` | Synthetic LabVIEW-style test rig: recording, Python rig, comparison evidence | labview-to-python |
| `real-vi/` | Four permissively licensed open-source `.vi` files with `sources.json` provenance and a proven Python port | labview-to-python, vi-fleet-discovery |
| `fleet/` | Fleet-scan fixture markers and expected counts for the VI tree (`.lvproj`, `.seq`) | vi-fleet-discovery |
| `model/` | MATLAB filter model, golden vectors, Python and C twins that reproduce them | matlab-to-code |
| `matlab-repo/` | 27 synthetic `.m` files (packages, classes, `private/`, dynamic calls, toolbox use) for repository-scale discovery | repo-discovery |
| `firmware-repo/` | 30 synthetic C/C++ files (ISR, registers, linker script, `#if` boards, C++ templates, vendor code) for repository-scale discovery | repo-discovery, bring-your-firmware |

## Run it

```bash
cd example-system
python -m unittest discover -s tests -v     # Python twin tests (always works)
make test                                   # C tests (needs gcc / cc)
python -m sim.sensor_node.demo              # prints 5 sample packets
```

Requirement IDs (`SN-REQ-xxx`), hazard IDs (`SN-HAZ-xxx`), and tracker IDs (`SN-BUG-xxx`,
`SN-CAP-xxx`) are cross-referenced so traceability demos work end to end.
