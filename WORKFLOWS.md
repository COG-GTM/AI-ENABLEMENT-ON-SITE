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
| Register | `/mcp-server register a GitHub server from integrations/mcp_config.example.json` | entry in `.devin/mcp_config.json`, token via `${VAR}` |

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

## Rules that hold across every workflow

- Numbers come from tools (`what_if.py`, `tracker_report.py`, `make test`), never typed by hand.
- Each stage names its input file explicitly so the next stage does not guess.
- Generated files go to `outputs/` (not committed) unless the stage edits the reference system itself.
- Finish any workflow with `python tools/check_repo.py`. `python tools/golden_path.py` runs every
  deterministic stage above end to end and leaves the evidence in `outputs/golden/REPORT.md`.
- To run a workflow on your own project: `Mimic workflow 1 on ../my-firmware; its docs are in ../my-firmware/docs`.
