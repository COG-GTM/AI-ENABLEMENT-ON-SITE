---
name: labview-to-python
description: Move a LabVIEW / TestStand test rig toward Python - inventory what the VI does, rebuild the behaviour in Python, prove it against a recording with bench_compare.py, and decide retain / wrap / port for each part. Not a converter.
argument-hint: "[path to .vi, exported .html, screenshots, TestStand .seq/.xml] [recording .csv/.tdms]"
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

LabVIEW migration for: `$ARGUMENTS`.

## What this is and is not

A `.vi` is a proprietary binary. There is no honest "point at the .vi, get Python" path and this skill does
not pretend to be one. What is real: the behaviour of a rig can be **reconstructed** from its exported
documentation, screenshots, and recorded data, then **proven** row by row against a recording of the
original. The deliverable is a Python rig with evidence, plus a written list of what was not proven.

Never present a reconstruction as equivalent until `tools/bench_compare.py` says PASS on a recording the
customer produced with the original rig.

## Step 1 - Inventory: what does the VI actually do?

Accept whatever the engineer can give you, best first. Ask for the next item only if the previous is missing.

| Input | How to get it | What Devin can read from it |
| --- | --- | --- |
| LabVIEW HTML/RTF export (`File > Print... > HTML`, "VI documentation") | Needs LabVIEW once, on their machine | Connector pane, every control/indicator with type and default, block-diagram image, SubVI list. **The best input.** Example: `example-system/bench/rig.vi.html` |
| Front-panel and block-diagram screenshots | Any machine with LabVIEW | Same content as above, less structured. Devin reads images; ask for one screenshot per case-structure frame |
| VI Analyzer report, `.lvproj` file list | LabVIEW | SubVI tree, dependencies, dead code |
| TestStand `.seq` (XML) or its report XML | Text, no tool needed | Step order, limits, loop counts, pass/fail rules |
| `.vi` file alone, `lvkit` installed | `lvkit describe X.vi`, `lvkit render X.vi -o outputs/X.svg`, `lvkit unresolved X.vi` | Signature, structures, SubVIs, a block-diagram drawing. No LabVIEW licence needed. See `integrations/lvkit.md` for what it can and cannot do |
| `.vi` file alone, no `lvkit` | - | Nothing. Ask for one of the rows above. Do not guess |
| Recording: CSV / TDMS / log of a real run, plus the raw samples that produced it | Their rig, one run | The **contract**. Without it nothing can be proven |

Write `outputs/<rig>-inventory.md`: purpose, inputs, outputs, constants (tolerances, setpoints, timeouts),
loop structure, error handling, instruments touched (VISA resource, DAQ channel, serial port), SubVIs, and an
explicit "unknown" list for anything the inputs did not show.

## Step 2 - Decide per part: retain, wrap, or port

Do this before writing code. One row per SubVI or block; most rigs have all three answers.

| Choice | When | What Python does |
| --- | --- | --- |
| **Retain** | FPGA, LabVIEW Real-Time, hardware-timed loops, DAQmx tasks with tight timing, anything certified as-is | Nothing. Leave it; document why |
| **Wrap** | The VI works and is trusted, but you want to call it from Python or run it in CI | Launch the built `.exe` (LabVIEW Run-Time Engine) or the TestStand sequence the way the bench already launches it, via `subprocess`; Python parses the report/CSV it writes. No rewrite |
| **Port** | Sequencing, arithmetic, limits, reporting, file I/O, instrument chatter over SCPI/serial that PyVISA or `pyserial` already handle | Rewrite in Python with injected instrument callbacks, prove against the recording |

Default recommendation shape: port the sequence and math, wrap the instrument driver if it is proprietary,
retain anything hardware-timed. Say this in the report even when the engineer asked for "convert all of it".

## Step 3 - Reconstruct in Python

Rules the example follows (`example-system/bench/rig.py`); copy them.

- Standard library first. `pyvisa`, `pyserial`, `nptdms` only when the real instrument needs them, and only
  behind a callback so tests never open hardware. On a laptop without PyPI, install them from a wheel folder
  the same way `integrations/lvkit.md` shows for lvkit (`pip download` on a connected machine, `--no-index
  --find-links` on the laptop).
- Constants from the inventory at the top of the file, named as the VI named them.
- Instruments are injected functions (`read_packet`, `set_chamber`, `settle`); the same code runs live and in replay.
- LabVIEW numerics are not Python numerics. Check each one: **Round To Nearest is ties-to-even**
  (`round()` in Python matches; `int(x + 0.5)` does not), integer division and modulo on negatives, `I16`
  saturation vs Python's unbounded `int`, `DBL` vs `SGL`, NaN handling in Mean/Max.
- Error cluster becomes an exception or a returned status; write down which, and what the VI did on error
  (skip step, abort, retry).
- Validate every input from a file: header names, row count cap, numeric range. Refuse, do not coerce.
- `--replay samples.csv --out outputs/x.csv` CLI so the comparison is one command.

What the common LabVIEW shapes become. Name the pattern in the inventory, then use the Python shape:

| On the block diagram | In Python |
| --- | --- |
| Flat/stacked sequence, For Loop over setpoints | Straight-line code, `for` loop (`run_soak` in `rig.py`) |
| State machine (While Loop + case structure on an enum) | `while` loop over an `Enum` state with one function per state; the shift register is a local variable |
| Producer/consumer, queued message handler | `queue.Queue` between a producer thread and a consumer loop; messages are a small dataclass, not a string |
| Event structure (button, value change) | Only matters if the port keeps a UI. For a bench script there is no UI: the sequence is driven by the CLI arguments and the input file |
| Error cluster wired through every node | One exception type; `try/finally` where the VI had a cleanup frame (chamber back to ambient in `rig.py`) |
| Shift register / feedback node | A variable that outlives the loop body, or a running-statistics object |
| Front panel indicators, charts | A CSV of results plus, if wanted, `/exec-deck` or a Markdown table; do not rebuild the panel |
| Local/global variables | Function arguments and return values. Note each one in the inventory: they hide dataflow and are a common source of ordering bugs in the original |
| SubVI | A function. Reuse across VIs becomes a module |

## Step 4 - Prove it against the recording

```bash
python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv
python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv --markdown > outputs/rig-compare.md
```

Exact match (`tol 0`) for integers and verdict strings; a stated tolerance for floats, with the reason
(`--tol mean_temp_cc=1` because the VI rounded before logging). A FAIL row in the recording must stay a
FAIL row in the reconstruction; the example keeps one on purpose (step 3 at 75 degC).

## Step 5 - Manual-review report

Write `outputs/<rig>-review.md` in the shape of `example-system/bench/RIG-REVIEW.md`: proven (with the
compare table), **not proven** (timing, instrument behaviour, error paths, cleanup, anything that only
happens on hardware), the retain/wrap/port table, and one recommendation line. Then hand it to
`/exec-deck` if leadership needs the decision.

## Worked example

`/labview-to-python example-system/bench/rig.vi.html example-system/bench/rig_recording.csv`
Inventory from the HTML export; port everything (no FPGA, no RT); `rig.py` replays 24 samples into 3 step
rows; `bench_compare` passes 9/9 columns exactly; review lists settle timing, VISA, CRC sync, and cleanup as
bench-only checks; recommendation "port, keep the VI until one live run matches".

What the example does and does not contain, so nobody mistakes it for more: `rig.vi.html` is written by
hand in the shape of a LabVIEW HTML export (the images are replaced by text); there is **no `.vi`** in this
repository, so the `lvkit` row above has not been exercised on the example, only on public sample VIs
(`integrations/lvkit.md`). TestStand `.seq` and TDMS are accepted inputs with no example file here. Every
number in the recording is synthetic. What the example proves is the method: the replay, the compare, the
FAIL row that has to survive, and the review that names what is still unproven.
