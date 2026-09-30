# Use case: a LabVIEW estate, from binary VIs to a migration plan and one proven rig

## Why

A LabVIEW estate is thousands of binary `.vi` files, `.lvproj` projects with RT and FPGA targets, and TestStand
sequences calling into them. Translating VIs one at a time misses the two things that make the migration hard:
**dependencies** (which VI calls which, what belongs to which target) and **LabVIEW built-ins** (vi.lib, DAQmx,
FPGA primitives) that have no one-line equivalent. This lane starts from the binaries, extracts what each VI
contains into JSON, builds the project-level dependency map, proposes a plan, and only then migrates one rig
and proves it against a recording. The target language stays selectable after decomposition: the map and
backlog say what depends on what; the plan says where it goes.

## When

- You have a folder tree of `.vi` (and `.lvproj`, `.lvlib`, `.lvclass`, TestStand `.seq`) and no current inventory.
- You need to answer "how many, what is in them, which leave LabVIEW first, what must stay on the target".
- You want a defensible plan before committing to Python, C#, C++, or keep-in-LabVIEW.

## What you need

- This repository, Python 3.10+, Devin Desktop. No network.
- `lvkit` (`integrations/lvkit.md`: offline wheel install, verified with 0.8.4). Without it the scanner still runs:
  every VI is `unreadable`, projects and sequences are still mapped, and the summary says `reader: lvkit absent`.
- Read-only access to the tree. Nothing is executed; LabVIEW is not needed.

## Step by step (fixture shown; substitute your tree)

| # | Do | Leaves behind |
| --- | --- | --- |
| 1 | `python tools/doctor.py` | confirms Python, optional `lvkit` |
| 2 | `/vi-fleet-discovery example-system --name demo-fleet` (or `python tools/vi_fleet_scan.py example-system --name demo-fleet`) | `outputs/demo-fleet-fleet-inventory.csv`, `-fleet-summary.json`, `-project-map.md`, `-dependency-map.json` + `.dot`, `-migration-backlog.json` + `.csv` |
| 3 | Read `outputs/demo-fleet-project-map.md`: shape, targets, sequence callers, entry points and call trees, external libraries, unresolved built-ins, leaf-first order | your understanding of the estate; paste the map into `/architecture-doc` for a written description |
| 4 | `python tools/prompt_pack.py --map outputs/demo-fleet-dependency-map.json --all` | `outputs/packs/demo-fleet/<ID>.md`: one bounded pack per VI (its evidence, callers, dependencies, open questions) |
| 5 | Pick the top `port` candidates from the backlog (priority = impact x readiness); decide the target per component | the migration plan (a section of `/exec-deck` or `/design-artifacts` ADR) |
| 6 | `/labview-to-python <rig.vi> <recording.csv>` for the first rig | `outputs/<rig>-notes.md`, `bench/<rig>.py`, `outputs/<rig>-compare.md` PASS/FAIL per column |
| 7 | `/track-and-report status of outputs/demo-fleet-migration-backlog.json` | tracker report; rescans keep ids and statuses |
| 8 | `/exec-deck Migration readiness from outputs/demo-fleet-fleet-summary.json` | leadership deck |

Repeat 6 to 8 per rig. Rerun step 2 any time: the backlog merges, ids and hand-set statuses survive.

## What the fixture shows (numbers from `outputs/golden/REPORT.md` and a run with lvkit 0.8.4)

- `example-system/`: 4 real, permissively licensed VIs (`real-vi/sources.json`), 1 synthetic `.lvproj` with
  My Computer, RT, chassis, and FPGA targets, 1 synthetic XML `.seq`.
- With lvkit: 4 of 4 VIs read, all `port`; 2 SubVI edges inside the tree, 6 external SubVIs in 4 libraries, 4 distinct
  unresolved built-ins, 0 cycles; callers and impact from `lvkit index`.
- Without lvkit: 4 `unreadable`, 6 dependency edges from the project and sequence files, 4 entry points; the report says so.
- One rig proven: `labview-to-python` stage replays 3 soak steps, 9/9 columns match the VI recording; `real-vi` replays
  39 cases, 10/10 columns match the diagram-derived table.

## How extraction works

`lvkit describe --format json --no-auto-vilib <file.vi>` returns the block-diagram nodes (with uids), wires (nets),
connector pane, and library/class facts; `lvkit unresolved --json` names the primitives and terminals lvkit could not
map. `tools/vi_fleet_scan.py` runs both per file (so one unreadable VI never stops the scan), then adds
`lvkit index` + `query` for callers and impact when a tree index succeeds. PyLabVIEW is an alternative extractor that
dumps RSRC blocks to XML; it does not give diagram semantics, so lvkit is used here (`integrations/lvkit.md`).

## What this does not prove

- The graph is static: SubVI references by path and library name, built-ins by primitive name. Dynamic calls
  (VI Server, Call By Reference) appear as unresolved, never guessed.
- `port / wrap / retain` are classifications with reasons, not decisions. A VI is migrated only when
  `tools/bench_compare.py` says PASS against a recording of the original.
- Hardware timing, FPGA, and RT determinism stay on the target (`retain`); the map tells you where that boundary is.

## Skills and files

`.devin/skills/vi-fleet-discovery/SKILL.md`, `.devin/skills/labview-to-python/SKILL.md`, `tools/vi_fleet_scan.py`,
`tools/prompt_pack.py`, `tools/bench_compare.py`, `example-system/fleet/`, `example-system/real-vi/`, `integrations/lvkit.md`,
`WORKFLOWS.md` sections 6 and 9, and the long-form deck `templates/deck-labview-migration-walkthrough.json`.
