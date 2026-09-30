# Workflows (pipelines)

A skill does one job. A workflow chains skills so that each stage's output file is the next stage's
input. Paste the prompts in order; Devin can also run a whole row when you ask for the end result
("swap the IMU and brief leadership"). Every stage runs offline against `example-system/`.

## 1. Design change: part swap to leadership brief

The most common embedded request: "what if we change this part?"

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Impact | `/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN` | `outputs/what-if-<slug>.md` (verdict, power/timing tables) |
| Artifacts | `/design-artifacts Update the ICD and hazards for the imu-c + CAN variant from the what-if file in outputs/` | edits to `example-system/docs/ICD.md`, `HAZARDS.md`, new `SN-REQ-*`/`SN-HAZ-*` IDs |
| Tests first | `/tdd Add the CAN framing to both firmware twins, tests first` | new tests + code in `example-system/src` and `sim/`, `make -C example-system test` green |
| Track | `/track-and-report Open a capability item for the CAN uplink linked to the new requirements` | `example-system/tracker.json` row, `python tools/tracker_report.py` |
| Brief | `/exec-deck Design review deck for the imu-c + CAN change: verdict, budgets, hazards, open items` | `outputs/<name>.deck.json` + `.html` |

## 2. Research to decision

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Research | `/research-brief Should we swap IMU A for IMU B? --sources example-system/parts,example-system/docs` | `outputs/<slug>.research.json`, `.md`, `.html` |
| Brief | `/exec-deck Leadership deck from the research JSON in outputs/: bottom line, evidence, open questions, ask` | `outputs/<slug>.deck.json` + `.html` |

## 3. Feature: spec to tests to code to document

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Specify | `/spec-driven Add a diagnostics packet with reinit count and uptime` | `specs/001-diagnostics-packet/{spec,plan,tasks}.md` |
| Build | `/tdd Implement specs/001-diagnostics-packet/tasks.md task by task` | tests then code in both twins, tasks ticked, tracker item closed |
| Document | `/architecture-doc Refresh example-system/docs/ARCHITECTURE.md for the diagnostics packet` | updated architecture doc with the new runtime view |

## 4. Connect a tool, then report

Works offline first (tracker file), then the same steps against a real system once your
administrator approves the token and the network path.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Connect | `/connect-tools I have a GitLab PAT; pull open issues for project 123 read-only` | dry-run request shown, then JSON in `outputs/` |
| Normalise | `Convert the issues JSON in outputs/ into the tracker schema (templates/tracker-item.json)` | items appended to `example-system/tracker.json` |
| Report | `/track-and-report Show open high-severity items and make a status report` | `python tools/tracker_report.py --markdown` output |
| Brief | `/exec-deck Status deck from the tracker: open vs closed, top five, asks` | `outputs/<name>.deck.json` + `.html` |

## 5. Stand up an MCP server by hand

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Run | `/mcp-server run-reference` | five JSON-RPC lines printed from `integrations/reference-mcp/handshake.jsonl` |
| Extend | `/mcp-server new-tool return the timing budget` | new tool + test in `integrations/reference-mcp/` |
| Host | `/mcp-server host` | Devin asks six questions (who needs it, network reach, approval, login, which file, read-only) and names the hosting model: laptop, shared entry, team-hosted, or vendor-hosted (`integrations/mcp-hosting.md`) |
| Register | `/mcp-server add github` | entry in `.devin/mcp_config.json` (or `.devin/mcp_config.local.json` for just you), token via `${env:VAR}`, checked by `python tools/doctor.py` |

## 6. LabVIEW / TestStand rig to Python (retain, wrap, or port)

Inputs: whatever you can get out of LabVIEW, best first: exported VI documentation (`File > Print >
HTML`), a TestStand `.seq`/XML export, front-panel and block-diagram screenshots, and a **recording** of
the rig's real output (CSV/TDMS). A bare `.vi` works only with the optional `lvkit` (see
`integrations/lvkit.md`). The recording is what proves the port; without one the result is a draft.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Inventory | `/labview-to-python example-system/bench/rig.vi.html example-system/bench/rig_recording.csv` | `outputs/<rig>-inventory.md`: SubVIs, instruments, timing, numeric semantics, one retain/wrap/port line per block |
| Reconstruct | `Write the Python rig for the inventory in outputs/, instruments as injected callbacks, --replay for recorded data` | `outputs/<rig>.py` (+ tests), same CSV columns as the VI |
| Prove | `python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv` then `python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv --markdown` | `outputs/<rig>-compare.md`: PASS/FAIL per column, max error, first divergent row |
| Review | `Write the manual-review report: what matched, what did not, what stays in LabVIEW and why` | `outputs/<rig>-review.md` (shape: `example-system/bench/RIG-REVIEW.md`) |
| Brief | `/exec-deck Migration readiness deck from the rig review in outputs/: retain / wrap / port per block, risks, next rig` | `outputs/<name>.deck.json` + `.html` |

Same lane, real `.vi` files, no recording (`example-system/real-vi/`): `python example-system/real-vi/inventory.py --check`
(binaries match `sources.json`; with `lvkit`, `VI-INVENTORY.md` is re-derived), then
`python example-system/real-vi/topic_filter.py --replay example-system/real-vi/cases.csv --out outputs/topic-filter-python.csv`
and `python tools/bench_compare.py example-system/real-vi/cases.csv outputs/topic-filter-python.csv`. PASS there means
the port agrees with the diagram reading and the project's own test VIs; `VI-REVIEW.md` lists what only a recorded run can settle.

## 7. MATLAB / Simulink model to C or Python, proven equivalent

Inputs: a `.m` function or `.slx` model, plus any vectors the model owner already has. If the team
runs Embedded Coder, the workflow reviews that generated C instead of writing a second copy.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Read the math | `/matlab-to-code example-system/model/moving_avg.m --target both` | `outputs/<model>-notes.md`: equations, indexing, rounding, saturation, fixed-point, warm-up (template: `example-system/model/MODEL-NOTES.md`) |
| Vectors | `Export golden vectors covering warm-up, extremes, rounding ties, negatives` | `outputs/<model>_vectors.csv` (or the owner's exported CSV) |
| Implement | `/tdd Implement the notes in C and Python, tests first, exact match on the vectors` | code in `example-system/src/` + `sim/`, `make -C example-system test` green |
| Prove | `python example-system/model/run_vectors.py --impl c --out outputs/model-c.csv` then `python tools/bench_compare.py example-system/model/filter_vectors.csv outputs/model-c.csv --markdown` | `outputs/<model>-compare.md` |
| Artifacts | `/design-artifacts Add the filter requirement and analysis evidence from the model notes in outputs/` | `SN-REQ-*` row + trace matrix still clean |

## 8. Bring your own firmware

Inputs: a C/C++ tree you can read (no board needed). Output: host-side tests that run on a laptop,
then every workflow above pointed at your code instead of `example-system/`.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Map | `/bring-your-firmware ../my-firmware` | `outputs/<tree>-firmware-map.md`: build system, toolchain, RTOS/SDK, HAL seam, what is host-buildable |
| Harness | `Stand up the host harness for the seam in the firmware map in outputs/, from templates/host-harness` | `../my-firmware/host-tests/` (Makefile, `hal_stub.c`, `test_main.c`), or GoogleTest/Unity if you already use one |
| First tests | `/tdd Nominal, one injected fault, one boundary case against the harness` | `make -C ../my-firmware/host-tests test` green |
| Then | workflows 1, 3, 4, 5 with `on ../my-firmware` | design artifacts, tracker items, decks about *your* system |

Host tests prove logic on a laptop; they do not prove timing, interrupts, MISRA, DO-178C objectives, or
behaviour on the target. `/bring-your-firmware` says so in its output.

## 9. LabVIEW estate: fleet discovery to the first ported rig

Inputs: a folder tree of `.vi` files (with any `.lvproj`, `.lvlib`, `.lvclass`, TestStand `.seq`, exported HTML, and
recordings that sit beside them), read-only. Optional `lvkit` (`integrations/lvkit.md`) turns file names into
diagram facts; without it every VI is still listed. Output: how many VIs, what is in each, which to port first,
and a backlog whose status the tracker tools report.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Discover | `/vi-fleet-discovery example-system --name demo-fleet` (your tree instead of `example-system`) | `outputs/demo-fleet-fleet-inventory.csv` (one row per VI: signature, SubVIs, unresolved primitives, structures, classification with reasons, complexity, priority, missing inputs), `outputs/demo-fleet-fleet-summary.json`, `outputs/demo-fleet-migration-backlog.json` + `.csv` |
| Choose | `Read outputs/demo-fleet-fleet-inventory.csv and write the fleet report: counts, top ten port candidates with reasons, what is missing` | `outputs/<name>-fleet-report.md`: the first sprint and the asks (recordings, HTML exports, passwords, binary .seq to convert) |
| Migrate one | `/labview-to-python <path to one candidate .vi> <its recording>` per rig, in backlog order | `outputs/<rig>-inventory.md`, `outputs/<rig>.py`, `outputs/<rig>-compare.md`, `outputs/<rig>-review.md` (workflow 6) |
| Status | `/track-and-report status of outputs/demo-fleet-migration-backlog.json` (or merge the `.csv` into the team tracker with `tools/tracker_import.py --from csv`) | `python tools/tracker_report.py --file outputs/demo-fleet-migration-backlog.json --markdown` output: open / in review / closed per component and severity |
| Brief | `/exec-deck Migration readiness from outputs/demo-fleet-fleet-summary.json and the fleet report` | `outputs/<name>.deck.json` + `.html`: estate size, classification split, first sprint, what is unproven |

`python tools/vi_fleet_scan.py --check` proves the scanner on the checked-in fixture (`example-system/fleet/`), with or
without lvkit. Classification is static evidence for ordering the work; a VI is ported only when
`tools/bench_compare.py` says PASS against a recording of the original.

## 10. MATLAB repository: discovery to the first proven function

Inputs: a folder tree of `.m` files (functions, scripts, `+packages`, `@classes`, `private/`), read-only. No MATLAB
licence is needed: the scanner is text-only. Output: what is in the repository, what calls what, which functions
can move first, one bounded prompt pack per unit, and a backlog whose status the tracker tools report.

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Discover | `/repo-discovery example-system/matlab-repo --lang matlab --name matlab-repo` (your tree instead of the fixture) | `outputs/matlab-repo-m-fleet-inventory.csv` (one row per file: kind, signature, calls by class, dynamic calls, callers, classification with reasons, complexity, priority, missing inputs), `-m-fleet-summary.json`, `-m-repo-map.md`, `-m-dependency-map.json` + `.dot`, `-m-migration-backlog.json` + `.csv` |
| Read the map | `Read outputs/matlab-repo-m-repo-map.md and write the repo report: counts, entry points, toolbox boundaries, top ten candidates with reasons, open questions` | `outputs/<name>-repo-report.md` |
| Pack | `python tools/prompt_pack.py --map outputs/matlab-repo-m-dependency-map.json --budget 8000` | `outputs/packs/matlab-repo-m/<ID>.md` one per backlog unit, `manifest.json` with bytes and tokens per pack |
| Migrate one | `/matlab-to-code <path from the pack> --target python` (or `c`, `both`), in leaf-first order | `outputs/<model>-notes.md`, vectors, code + tests, `outputs/<model>-compare.md` (workflow 7) |
| Status | `/track-and-report status of outputs/matlab-repo-m-migration-backlog.json` | `python tools/tracker_report.py --file ... --markdown` output |
| Brief | `/exec-deck Migration readiness from outputs/matlab-repo-m-fleet-summary.json and the repo report` | `outputs/<name>.deck.json` + `.html` |

`python tools/m_fleet_scan.py --check` proves the scanner on the fixture (`example-system/matlab-repo/`, 27 files built to
exercise packages, classes, private folders, dynamic calls, toolbox use, shadowing, and a malformed file). The graph is
static candidate evidence; a function is migrated only when `tools/bench_compare.py` says PASS on the owner's vectors.

## 11. C/C++ repository: discovery to host tests and a proven twin

Inputs: a C/C++ tree (sources, headers, Makefile/CMake, linker script), read-only; a host `gcc` is optional and adds an
include-graph cross-check. Output: which files are host-testable, which are target-only, where the HAL seam is, and a
backlog. There is no C-to-Python translator here: a Python implementation is a **behavioural twin** proven against the
C on shared tests and vectors (`example-system/src` and `sim/` are the finished example).

| Stage | Paste | Leaves behind |
| --- | --- | --- |
| Discover | `/repo-discovery example-system/firmware-repo --lang c --name firmware-repo` (add `--cflags "-DBOARD_REV_C"` when your headers need the target's flags) | `outputs/firmware-repo-c-fleet-inventory.csv` (per file: functions, includes, calls by class, ISR / volatile / register / asm / linker markers, callers, classification with reasons), `-c-fleet-summary.json`, `-c-repo-map.md` (entry points, seam candidates, target-only files, leaf-first order), `-c-dependency-map.json` + `.dot`, `-c-migration-backlog.json` + `.csv` |
| Harness | `/bring-your-firmware example-system/firmware-repo` using the seam candidates in the repo map | `outputs/<tree>-firmware-map.md`, `host-tests/` beside the tree (from `templates/host-harness/`) |
| Pack | `python tools/prompt_pack.py --map outputs/firmware-repo-c-dependency-map.json` | `outputs/packs/firmware-repo-c/<ID>.md`, `manifest.json` |
| Port one | `/tdd Host-test <unit from the pack> against the harness, then write the Python twin, tests first, exact match on the vectors` in leaf-first order | tests + code, `make test` green, `outputs/<unit>-compare.md` |
| Status, brief | `/track-and-report status of outputs/firmware-repo-c-migration-backlog.json`, then `/exec-deck Migration readiness from outputs/firmware-repo-c-fleet-summary.json` | tracker report, deck |

`python tools/c_fleet_scan.py --check` proves the scanner on the fixture (`example-system/firmware-repo/`, 30 files: ISR,
memory-mapped registers, linker script, `#if` board variants, C++ templates and overloads, vendor code, K&R legacy, a
non-UTF-8 file). Host tests prove logic on a laptop, not timing, interrupts, or behaviour on the target.

## 12. Reusable pipeline: scan, pack, run, compare, report - unattended

Inputs: any tree the three scanners understand (`--lang c|matlab|labview`) and, optionally, a per-unit agent command.
Output: a journaled, resumable run a team can own in its own repository or CI, that never sends the whole tree to an
agent and never claims a unit is done without evidence.

| Stage | Paste or run | Leaves behind |
| --- | --- | --- |
| Dry run | `python tools/pipeline_run.py --lang c --tree example-system/firmware-repo --name firmware-repo` | `outputs/pipeline/firmware-repo/`: `scan/` (scanner outputs), `packs/` (one per unit), `REPORT.md`, `state.json`, `journal.jsonl`, `firmware-repo-backlog-status.json`; agent stage recorded as **dry run**, every unit `skipped` |
| Resume | same command with `--resume` (add `--from-stage pack` to force a stage) | unchanged stages skipped by input hash, journal says which |
| With an agent | `--agent-cmd "<your command> {pack} {results} {id} {unit}"` (each unit reads one pack, writes `results/<id>/result.json`) and optionally `--compare-cmd "<your check> {id} {unit}"` | `results/<id>/`, `REPORT.md` with done / blocked / failed / proven per unit; backlog items with a passing comparison move to `in_review`, never to `closed` |
| In CI | `.github/workflows/migration-scan.yml` (manual or weekly; scan -> pack -> report on a tree you name, artifacts uploaded) | the same folder as a build artifact |
| Status | `python tools/tracker_report.py --file outputs/pipeline/firmware-repo/firmware-repo-backlog-status.json` | open / in review per component and severity |

`tools/golden_path.py` runs the dry run and the resume on the firmware fixture. The comparison of approaches (structured
intermediate files, a reference repository, skill files, a graph-style controlled flow) and the token-control rules are in
`use-cases/reusable-pipeline/README.md`.

## Rules that hold across every workflow

- Numbers come from tools (`what_if.py`, `tracker_report.py`, `make test`), never typed by hand.
- Each stage names its input file explicitly so the next stage does not guess.
- Generated files go to `outputs/` (not committed) unless the stage edits the reference system itself.
- Finish any workflow with `python tools/check_repo.py`. `python tools/golden_path.py` runs every
  deterministic stage above end to end and leaves the evidence in `outputs/golden/REPORT.md`.
- To run a workflow on your own project: `Mimic workflow 1 on ../my-firmware; its docs are in ../my-firmware/docs`.
