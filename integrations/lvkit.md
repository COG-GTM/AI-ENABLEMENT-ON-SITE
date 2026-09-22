# lvkit: reading LabVIEW `.vi` files without LabVIEW (optional)

`lvkit` is an open-source (Apache-2.0) Python tool that parses LabVIEW `.vi` binaries and prints what
is inside: connector pane, controls and indicators with types, structures, SubVI calls, and a
block-diagram drawing. It does not need a LabVIEW licence. `/labview-to-python` uses it as an
**inventory** step when a team has only `.vi` files and no exported documentation.

Source: <https://github.com/pragmatest-dev/lvkit>. Package: <https://pypi.org/project/lvkit/>.
Tested here: version 0.8.4, Python 3.12, Linux. Alpha software; expect rough edges.

## What it did on this laptop

| Command | Result on the sample VIs tried | Use it for |
| --- | --- | --- |
| `lvkit describe X.vi` | Worked on every sample: signature, properties, health flags (`is_broken`), inputs/outputs, structures, SubVIs | The inventory table in `outputs/<rig>-inventory.md` |
| `lvkit render X.vi -o outputs/X.svg` | Worked on every sample: block-diagram drawing as SVG (`--format html` gives an interactive viewer) | A diagram Devin and the engineer can both read |
| `lvkit unresolved X.vi` | Worked: lists primitives and `vi.lib` VIs the tool does not know | Tells you which parts `generate` will get wrong before you run it |
| `lvkit diff old.vi new.vi` | Not exercised here | Reviewing a VI change without opening LabVIEW |
| `lvkit generate X.vi -o outputs/` | Produced Python for 3 of 4 samples, failed on 1 (unmapped primitive). Output was structurally right and semantically thin: the shape of loops and calls, not the maths, error handling, or instrument behaviour | Optional scaffolding to read, never the deliverable. The Python that ships is written from the inventory and proven against a recording (`tools/bench_compare.py`) |
| `lvkit mcp --selftest` | Initialised and listed 8 tools (`read_vi`, `render`, `diff`, `unresolved`, `query`, `index`, ...) | Registering the server so Devin can inspect VIs directly (below) |

What it cannot do: run a VI, prove behaviour, understand FPGA/Real-Time/DAQmx timing, or replace the
recording. Treat its output like a good set of screenshots: evidence of structure, not of behaviour.

## Install

Online laptop:

```bash
python3 -m pip install lvkit
lvkit --version
```

Offline laptop (PyPI blocked): an administrator downloads the wheels once on a machine with the **same
OS, architecture, and Python minor version**, copies the folder over, and installs from it.

```bash
# on the connected machine
python3 -m pip download lvkit -d lvkit-wheels        # ~32 wheels, ~20 MB; 5 are platform-specific
# on the laptop
python3 -m pip install --no-index --find-links lvkit-wheels lvkit
```

Do not vendor the wheels into this repository: they are platform-specific, alpha, and 20 MB.
`tools/doctor.py` lists lvkit under "Optional tools" (OK when found, SKIP when not); absent is never an error.

## Register the MCP server (optional, ask first)

`lvkit mcp` speaks MCP over stdio. To expose it to Devin, copy this entry into `.devin/mcp_config.json`
next to `reference-system`, replacing `path/to/vi-folder` with the folder that holds the VIs. Remove it
when the work is done.

```json
"lvkit": {
  "command": "lvkit",
  "args": ["mcp", "path/to/vi-folder"]
}
```

Check it with `lvkit mcp --selftest` before registering; a broken install otherwise registers zero tools
silently. The 8 tools it listed here (`list_projects`, `index`, `query`, `query_schema`, `read_vi`,
`render`, `diff`, `unresolved`) inspect VIs; none edits a `.vi`. It is a local process with no
network lane of its own.

## When you do not have lvkit

Ask the LabVIEW owner for one of these instead; `/labview-to-python` accepts all of them:

1. `File > Print... > HTML` from LabVIEW ("VI documentation", include block diagram) - the best input.
2. Front-panel and block-diagram screenshots, one per case-structure frame.
3. A VI Analyzer report or the `.lvproj` file list.
4. The TestStand sequence file (`.seq`, XML) and one run report.
5. Always: a recording of one real run (CSV/TDMS) plus the raw samples that produced it.

Item 5 is the one that cannot be skipped; everything else only describes the rig, the recording proves it.
