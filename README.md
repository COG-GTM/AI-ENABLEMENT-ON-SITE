# Devin Desktop workflow library

Ready-to-run workflows for Devin Desktop (Devin Local agent) in a Federal environment: research
briefs, executive decks (HTML and PPTX), embedded design artifacts, what-if part swaps, spec-driven and
test-driven development, architecture docs, bug/capability tracking, connecting to your tools
(CLI, REST API, MCP), and three lanes for the tools embedded teams already use: your own C/C++
firmware, MATLAB/Simulink models, and LabVIEW/TestStand rigs. Everything runs offline against a
synthetic reference system. No customer data.

This is a reference repository, not a product. Every skill is a procedure Devin follows; the
sensor node in `example-system/` is what it practises on. The last step of every workflow is
"now do this on my project".

## Get the files (once)

Devin Desktop works on a folder on your laptop, so the repository has to be on the machine. Reading
it on GitHub is fine; running it needs a local copy. Pick one:

1. **No git needed:** on the GitHub page click the green **Code** button, **Download ZIP**, unzip it
   anywhere, and open that folder in Devin Desktop.
2. **Have git:** `git clone https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE.git`, then open the folder.
3. **Let Devin do it:** paste the repository URL into Devin Desktop and say `clone this and open it`.
   Works only if the laptop is allowed to reach github.com.

Nothing to install afterwards: Python 3.10+ is the only requirement.

## Start here (2 minutes)

1. Open the folder in Devin Desktop.
2. Devin reads `AGENTS.md` automatically and finds the skills under `.devin/skills/`.
3. Paste these three prompts, in order:

```
Reference this repo. What can you do here? Run the checks and show me.
/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN
/exec-deck Design review deck for the imu-c + CAN change: verdict, budgets, hazards, open items
```

Two minutes later you have a readiness check, a go/no-go analysis with recomputed budgets, and a
leadership deck open in the preview. Chained prompts like these are **workflows**; the eight we ship
are in `WORKFLOWS.md`. Showing this to a room? Follow `WALKTHROUGH.md`. Live in C, MATLAB, or
LabVIEW all day? Jump to [Your tools](#your-tools-cc-matlabsimulink-labviewteststand).

If you do not write code: the prompts in this file are all you need. Skip "Prove it works" and
"Where things live"; Devin runs those commands for you.

## The skills

One folder per skill under `.devin/skills/<name>/SKILL.md`. Type the slash command, or say it in
plain English; `AGENTS.md` maps phrases like "make me a deck" to the right skill.

| Skill | What it does | Reads from | Leaves behind |
| --- | --- | --- | --- |
| `/tour` | Checks the laptop, runs every test, opens the example deck, explains what to do next | whole repo | `outputs/example-deck.html` |
| `/research-brief` | Answers a question from local files (and approved web sources); every finding has a source and a confidence, or the renderer rejects it | files you name with `--sources` | `outputs/<slug>.research.{json,md,html}` |
| `/exec-deck` | Turns requirements, hazards, budgets, tracker, or a research brief into a leadership deck; numbers are recomputed by tools, one idea per slide, a source under every number | `example-system/docs/`, `tracker.json`, `outputs/` | `outputs/<name>.deck.json`, `.html`, optional `.pptx` |
| `/design-artifacts` | Adds or updates requirements (`SN-REQ-*`), ICD sections, ADRs, hazard/FMEA rows (`SN-HAZ-*`), power and timing budget lines, all cross-referenced by ID | `example-system/docs/` | edits to `SRS.md`, `ICD.md`, `HAZARDS.md`, `ADR-*.md`, budgets |
| `/what-if-part-swap` | Recomputes power and timing for a chip/sensor/device change, flags bus, voltage, scale-factor, package, and hazard impacts, says go / no-go / go with conditions | `example-system/parts/*.json`, `docs/` | `outputs/what-if-<slug>.md` |
| `/spec-driven` | Spec, then plan, then tasks, then implement one task at a time with tests; the spec stays the source of truth | `templates/spec.md`, `templates/plan.md` | `specs/NNN-<slug>/{spec,plan,tasks}.md` |
| `/tdd` | Red, green, refactor on Python or C; writes the failing test first, then the smallest change to both firmware twins | `example-system/src/`, `sim/`, `tests/` | new tests and code, `make -C example-system test` green |
| `/architecture-doc` | Short arc42 / C4 document derived from the actual code: module table, runtime view, decisions, risks | source tree | `example-system/docs/ARCHITECTURE.md` (or yours) |
| `/track-and-report` | Bugs, defects, and capabilities in one JSON file linked to requirement and hazard IDs; status reports in text, Markdown, JSON | `example-system/tracker.json` | tracker rows, `python tools/tracker_report.py` output |
| `/connect-tools` | Picks the lane (REST/curl, vendor CLI, MCP) and credential (PAT, API token, OAuth) for Jira, Confluence, GitLab, GitHub, Azure DevOps; read-only, token never in chat, dry run first | `integrations/` recipes | redacted request shown, then JSON in `outputs/` |
| `/mcp-server` | Runs the offline reference MCP server, adds a tool to it, or registers a server by hand in `.devin/mcp_config.json`; no marketplace needed | `integrations/reference-mcp/` | new tool + test, config entry |
| `/labview-to-python` | Inventories what a VI or TestStand sequence does, rebuilds that behaviour in Python, proves it against a recording of the real rig, and says retain / wrap / port for each part. Not a converter | exported VI docs (HTML), screenshots, TestStand XML, a recording CSV; a bare `.vi` with optional `lvkit` | `outputs/<rig>-inventory.md`, `rig.py`, `<rig>-compare.md`, `<rig>-review.md` |
| `/matlab-to-code` | Reads a `.m` or `.slx`, writes down the numeric semantics (indexing, rounding, saturation, fixed point), exports golden vectors, implements in C and/or Python, proves equivalence; reviews Embedded Coder output instead of re-porting it | `example-system/model/` or your model | `outputs/<model>-notes.md`, vectors CSV, code + tests, compare report |
| `/bring-your-firmware` | Maps your C/C++ tree (build, toolchain, RTOS, HAL seam), stands up a host-side harness with stubbed hardware from `templates/host-harness/`, gets three tests running on a laptop, then hands over to `/tdd`, `/design-artifacts`, `/track-and-report`, `/exec-deck` | your firmware tree (read-only first) | `outputs/<tree>-firmware-map.md`, `host-tests/` in your tree |

Full prompt list, ready to paste:

| You want | Paste this |
| --- | --- |
| A tour | `/tour` or `Reference this repo. What can you do here? Run the checks and show me.` |
| Research | `/research-brief Should we swap IMU A for IMU B? --sources example-system/parts,example-system/docs` |
| Executive deck (HTML + PPTX) | `/exec-deck Build a leadership deck on the sensor node: requirements, top hazards, power budget, open bugs` |
| Design artifacts | `/design-artifacts Add a requirement and hazard for low-battery shutdown at 3.0 V` |
| What-if a new chip | `/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN` |
| Spec first | `/spec-driven Add a diagnostics packet with reinit count and uptime` |
| Tests first | `/tdd Make the temperature fault flag stay set until two in-range readings` |
| Architecture doc | `/architecture-doc Document the sensor node firmware` |
| Bugs and status | `/track-and-report Show open high-severity items and make a status report` |
| Connect a tool | `/connect-tools I have a GitLab PAT; pull open issues for project 123 read-only` |
| MCP server by hand | `/mcp-server run-reference` then `/mcp-server new-tool return the timing budget` |
| Leave LabVIEW, safely | `/labview-to-python example-system/bench/rig.vi.html example-system/bench/rig_recording.csv` |
| MATLAB model to C | `/matlab-to-code example-system/model/moving_avg.m --target c` |
| Your firmware, host tests | `/bring-your-firmware ../my-firmware` |
| Mimic on your code | `Mimic the /design-artifacts workflow on my project in ../my-firmware` |

## The workflows

A skill does one job. A workflow chains skills so each stage's output file is the next stage's
input. Full tables with every prompt are in `WORKFLOWS.md`; here is what each one is for.

| # | Workflow | Skills in order | The question it answers |
| --- | --- | --- | --- |
| 1 | Design change to leadership brief | `/what-if-part-swap`, `/design-artifacts`, `/tdd`, `/track-and-report`, `/exec-deck` | "What if we change this part, and what do I tell the review board?" |
| 2 | Research to decision | `/research-brief`, `/exec-deck` | "What do we know, with sources, and what is the recommendation?" |
| 3 | Feature: spec to tests to code to document | `/spec-driven`, `/tdd`, `/architecture-doc` | "Add this feature properly, with the paperwork kept honest." |
| 4 | Connect a tool, then report | `/connect-tools`, convert to the tracker schema (`tools/tracker_import.py`), `/track-and-report`, `/exec-deck` | "Pull our real issues, read-only, and turn them into a status deck." |
| 5 | Stand up an MCP server by hand | `/mcp-server` | "Show me the whole MCP protocol in one file, then add a tool to it." |
| 6 | LabVIEW / TestStand rig to Python | `/labview-to-python`, `tools/bench_compare.py`, `/exec-deck` | "Which parts of this rig can leave LabVIEW, and how do I prove the Python does the same thing?" |
| 7 | MATLAB / Simulink model to code | `/matlab-to-code`, `/tdd`, `tools/bench_compare.py`, `/design-artifacts` | "Does the C match the model, bit for bit, on the vectors the model owner signed off?" |
| 8 | Bring your own firmware | `/bring-your-firmware`, `/tdd`, then workflows 1 to 5 | "Run all of this on our code, on a laptop, without a board." |

Ask for the end result and Devin runs the whole row: `Swap the IMU for imu-c and brief leadership`.

## How an embedded engineer uses this

The repository is a practice board. Run the moves here, then point them at your own firmware.

- **"What happens if we swap this chip?"** Add a JSON file for the real part to
  `example-system/parts/` (data-sheet values: mA active and sleep, bus, voltage, package), then
  `/what-if-part-swap Replace imu-a with <your-part>`. Devin recomputes the power and timing budget,
  flags bus, voltage, and scale-factor breaks, lists which documents and drivers change, and gives a
  verdict. Try it now with the parts already there: `imu-a` (current), `imu-b`, `imu-c`, `can-xcvr`.
- **"Write the test before the fix."** `/tdd Make the temperature fault flag latch until two good
  readings`. Devin writes the failing test in `example-system/tests/`, makes the smallest change to
  both twins (`src/*.c` and `sim/sensor_node/*.py`), and runs `make -C example-system test` red then
  green. Hardware is a callback, so nothing needs a board.
- **"Add a feature properly."** `/spec-driven Add a diagnostics packet`. Look at
  `specs/001-diagnostics-packet/` first: that is a finished spec, plan, and task list, each task tied
  to a requirement ID. Then `/tdd Implement specs/001-diagnostics-packet/tasks.md task by task`.
- **"Keep the paperwork honest."** `/design-artifacts` adds a requirement, hazard, or budget line with
  an ID. `python tools/trace_matrix.py` then fails if a requirement has no test, a high-risk hazard has
  no mitigation, an open hazard has no tracker item, or a document names a test that does not exist.
- **"Brief the boss."** `/exec-deck` turns the same files into a deck with recomputed numbers and a
  source line under each. HTML opens in the preview; say "as PowerPoint" and it also writes a `.pptx`.
- **On your own code:** `Mimic workflow 1 on ../my-firmware; its docs are in ../my-firmware/docs`.
  The skills are generic; only `example-system/` is the practice system.

## Your tools: C/C++, MATLAB/Simulink, LabVIEW/TestStand

Embedded teams split the work across three toolsets, and each has its own seat. Python is the glue
that lets Devin replay, compare, and report across all of them without touching the target.

```
  MATLAB / Simulink            C / C++ firmware              LabVIEW / TestStand
  algorithm, equations,        what ships on the target;     the bench: instruments,
  reference behaviour          HAL between logic and hw      sequences, verdicts, logs
        |                            |                              |
   /matlab-to-code            /bring-your-firmware           /labview-to-python
        |                            |                              |
        +----------- Python: replay, compare, stub, report ---------+
                                     |
              tools/bench_compare.py  ->  /tdd  ->  /design-artifacts  ->  /exec-deck
```

Each lane has a finished example in this repository so you can see the shape before you bring your own.

| Lane | Open this folder | What is in it |
| --- | --- | --- |
| C/C++ firmware | `templates/host-harness/` | `Makefile`, `hal_stub.c/.h` (scripted SPI/I2C/UART/GPIO, deterministic clock, fault injection), `harness.h` (tiny assert macros), `test_main.c` (58 checks against `example-system/src`). Point `FW_SRC`/`FW_INC` at your tree and rewrite section 2 only |
| MATLAB / Simulink | `example-system/model/` | `moving_avg.m` (the model), `export_vectors.m` (how the owner exports vectors), `filter_vectors.csv` (26 rows: warm-up, extremes, negatives, rounding), `run_vectors.py` (replays through the Python twin or the C via `vectors_driver.c`), `MODEL-NOTES.md` (the numeric-semantics table) |
| LabVIEW / TestStand | `example-system/bench/` | `rig.vi.html` (what LabVIEW's own HTML export of a thermal-soak VI looks like), `rig_samples.csv` (24 raw readings), `rig_recording.csv` (the VI's own 3-step results, one step failing on purpose), `rig.py` (the Python port, instruments as callbacks, `--replay`), `RIG-REVIEW.md` (the manual review); its test is `example-system/tests/test_rig.py` |
| LabVIEW, real `.vi` files | `example-system/real-vi/` | Four real VIs from a public open-source LabVIEW project (0BSD licence, provenance in `sources.json`), `VI-INVENTORY.md` (what `lvkit` read out of them, generated), `topic_filter.py` (the Python port of two of them), `cases.csv` (39 expected rows: 9 from the project's own test VIs, 30 from the MQTT specification), `VI-REVIEW.md` (what held, what did not, what is still unproven); its test is `example-system/tests/test_topic_filter.py` |
| Shared | `tools/bench_compare.py` | Two CSVs in, PASS/FAIL per column out, with tolerance per column, max error, and the first divergent row. Standard library only |

### C/C++: run the workflows on your firmware

Most firmware logic (framing, filtering, state machines, fault handling) does not need a board; it
needs the hardware calls replaced by something deterministic. `/bring-your-firmware` finds that seam
in your tree and builds the harness:

1. **Map, read-only.** Build system (Make/CMake/IAR/Keil/vendor IDE), toolchain, RTOS or vendor SDK,
   where the HAL is, which files are pure logic. Written to `outputs/<tree>-firmware-map.md` with the file
   that proves each claim.
2. **Pick the seam.** Link-time stubs (your code calls `hal_spi_transfer()`, the harness provides it),
   callback injection (like `example-system/src/node.h`), or refactor-first when hardware calls are
   tangled into the logic.
3. **Harness.** Copy `templates/host-harness/`, keep sections 1 and 3 of `test_main.c`, rewrite the
   adapters in section 2 for your HAL. Already on GoogleTest, Unity, or Ceedling? It uses yours.
4. **Three tests:** nominal, one injected fault, one boundary. `make test` green on the laptop.
5. **Then** `/tdd` for the next change, `/design-artifacts` for the paperwork, `/track-and-report` for
   the defect list, `/exec-deck` for the review.

What host tests do not prove: timing, interrupt behaviour, MISRA or DO-178C objectives, compiler
or target specifics. The skill says so in its output; keep the on-target tests you have.

### MATLAB / Simulink: from model to code you can trust

The algorithm owner works in MATLAB; the firmware is C. The usual failure is not syntax, it is
numeric semantics: one-based indexing, `fix` vs `round` vs C truncation, `int16` saturation, fixed-point
word lengths, accumulator width, warm-up behaviour. `/matlab-to-code` makes those explicit before any
code is written:

- **`.m` files** are read directly. **`.slx` files** are ZIP archives of XML; the skill inventories
  blocks, sample times, and data types from them without MATLAB.
- **Golden vectors** come from the model owner (`export_vectors.m` shows how) and cover the edges:
  warm-up, extremes, negatives, rounding ties.
- **Implementation** goes through `/tdd`, then `run_vectors.py` + `bench_compare.py` prove the C and
  Python match the vectors exactly (tolerance `0` for integer outputs).
- **Already using Embedded Coder?** The skill reviews the generated C against the same vectors instead
  of writing a second implementation.

See `example-system/model/MODEL-NOTES.md` for the table the skill produces.

### LabVIEW / TestStand: the honest path out

This is the hard one, so here is exactly what is and is not possible.

**A `.vi` is a proprietary binary.** There is no reliable "point at the `.vi`, get Python" step, and
this repository does not pretend there is. What works is a **port proven against a recording**: Devin
learns what the rig does, rebuilds that behaviour in Python, runs the Python on the same input data the
rig saw, and compares the two outputs row by row. The recording, not the source, is the proof.

**Three ways to get a VI's contents in front of Devin**, best first:

| You have | How to get it out | What Devin can do with it |
| --- | --- | --- |
| LabVIEW on some machine | `File > Print... > HTML`, include block diagram and connector pane. `example-system/bench/rig.vi.html` is a hand-written stand-in for that export (text where the images would be) | Read every control, indicator, constant, structure, and SubVI name; build the inventory |
| Screenshots only | Front panel plus one block-diagram screenshot per case frame | Same as above, read from the images; less exact on constants |
| Only the `.vi` file, no LabVIEW | Optional `lvkit` (`integrations/lvkit.md`): `lvkit describe`, `lvkit render`, `lvkit unresolved` | Signature, structures, SubVI list, a block-diagram SVG. No LabVIEW licence needed |

Plus, always: a TestStand `.seq`/XML export if the VI is sequenced by TestStand, a VI Analyzer report if
you have one, and **a recording** (CSV/TDMS of one real run, with the raw samples that produced it).
Without a recording the result is a draft, and the skill labels it as one.

**What we found when we tried `lvkit`** (open source, Apache-2.0, version 0.8.4, alpha): it read
every sample `.vi` we gave it without LabVIEW; `describe` and `render` worked on 4 of 4; its Python
`generate` produced skeletal code on 3 of 4 and failed on 1. So the skill uses it for **inventory**
(what is in the VI) and never as the deliverable. Its output is evidence of structure, like a good set
of screenshots; it is not evidence of behaviour. Details, install (online and offline), and the optional
MCP registration are in `integrations/lvkit.md`. Not installed? Everything still works from the
HTML export or screenshots.

**Then we tried it on real VIs we did not write.** `example-system/real-vi/` holds four `.vi` files from
a public open-source LabVIEW MQTT broker (0BSD licence): the two VIs that validate and match topic filters,
and the project's own two requirement-test VIs. Only the binaries, no export, no recording. `lvkit`
inventoried all four and rendered their diagrams; `lvkit generate` failed on all four. The
Python port was written from the inventory and the drawing, and `bench_compare.py` says it agrees with
the diagram on 39 of 39 rows, including the 9 verdicts recovered from the project's own tests. It also
surfaced a finding: at that commit the project uses `+` and `#` the opposite way round from MQTT 3.1.1,
consistently, in code and tests. What this does **not** show is runtime equivalence: nobody ran the
original VIs, and `VI-REVIEW.md` lists the five diagram readings that one recorded run each would settle.
That is the honest shape of a real port: inventory works, generation does not, the human reads the
drawing, the compare proves agreement with the reading, the recording proves the reading.

**Retain, wrap, or port.** The skill gives one of three answers per SubVI or block, and the review
report records why:

| Answer | When | Result |
| --- | --- | --- |
| **Port** | Pure logic: sequencing, parsing, maths, verdicts, report generation | Python, proven against the recording |
| **Wrap** | Works, cannot be re-verified cheaply, or depends on an NI driver you keep (DAQmx, VISA instrument with LabVIEW-only driver) | Python calls the VI/TestStand executable or talks to the instrument directly over VISA; Python owns sequencing and results |
| **Retain** | FPGA, Real-Time targets, deterministic timing loops, hardware-timed DAQ, anything the recording cannot exercise | Stays in LabVIEW; Python consumes its output files |

**Numeric semantics to watch**, written into the inventory every time: `Round To Nearest` sends x.5 to
the even integer (Python's `round()` matches, `int(x + 0.5)` does not); `I16`/`I32` have fixed widths
while Python's `int` does not; `SGL` vs `DBL`; NaN inside `Mean`/`Max`; and what the error cluster did
downstream (skip the step, stop the run, or carry on). The example rig hits the first one on step 1.

**Try it on the example**: `/labview-to-python example-system/bench/rig.vi.html
example-system/bench/rig_recording.csv`. The recording has step 3 failing (a 75 °C setpoint the node
could not hold); the Python port reproduces that FAIL, and `bench_compare.py` shows 9 of 9 columns
matching. A port that turned the FAIL into a PASS would be caught on the spot. The manual review is
`example-system/bench/RIG-REVIEW.md`; yours will look like it. The rig example is synthetic end to end and
the skill says so; the real `.vi` files live in `example-system/real-vi/` and stop at the diagram reading.
No TestStand or TDMS file ships here.

## Where things live

```
AGENTS.md            Devin reads this first: rules + which skill to use for what (under 40 lines)
WORKFLOWS.md         the 8 pipelines above, with every prompt and what each stage leaves behind
WALKTHROUGH.md       25-minute speaker path for showing the repo live, with a recovery move per beat
SECURITY.md          data-handling and least-privilege rules
.devin/skills/       one folder per skill, one SKILL.md each (cap: 15); open one to see the procedure
.devin/mcp_config.json  registers the offline reference MCP server
example-system/      the synthetic battery sensor node everything practises on
  docs/              SRS.md (requirements), ICD.md (interfaces), HAZARDS.md (FMEA), ADR-*.md (decisions),
                     POWER-BUDGET.md, TIMING.md, ARCHITECTURE.md
  parts/             one JSON per part (mcu-m0, imu-a/b/c, temp-x, can-xcvr): the numbers what-if uses
  README.md          how the node works and how to build and test it
  src/               C firmware: node.c, packet.c, filter.c and their .h headers (host-buildable, hardware via callbacks)
  sim/sensor_node/   Python twin of the same firmware (node.py, packet.py, filter.py, demo.py)
  tests/             test_node.py, test_packet.py, test_filter.py, test_firmware.c, test_model_equivalence.py, test_rig.py
  model/             MATLAB lane: moving_avg.m, export_vectors.m, filter_vectors.csv, run_vectors.py, MODEL-NOTES.md
  bench/             LabVIEW lane: rig.vi.html (exported VI docs), rig_samples.csv, rig_recording.csv, rig.py, RIG-REVIEW.md
  real-vi/           LabVIEW lane on real VIs: 4 .vi files (public, 0BSD), sources.json, VI-INVENTORY.md, topic_filter.py, cases.csv, VI-REVIEW.md
  tracker.json       bugs (SN-BUG-*) and capabilities (SN-CAP-*) linked to requirement and hazard IDs
  Makefile           make test runs both twins
specs/               001-diagnostics-packet/: a finished spec -> plan -> tasks example
tools/               small Python scripts the skills call. Standard library only.
  doctor.py          is this laptop ready?              check_repo.py    validates the whole repo
  what_if.py         power/timing recompute              trace_matrix.py  requirement -> hazard -> test -> tracker
  build_deck.py      JSON outline -> HTML deck           export_pptx.py   same outline -> PPTX
  research_brief.py  research JSON -> MD + HTML brief    tracker_report.py status report
  golden_path.py     runs every workflow end to end      tests/           tests for the tools
  tracker_import.py  Jira / GitLab / Azure DevOps / CSV export -> tracker.json schema
  bench_compare.py   two CSVs -> PASS/FAIL per column (tolerances, max error, first divergent row)
integrations/        README.md (which lane, which credential), curl-recipes.md, cli-recipes.md,
                     rest_client.py (read-only, redacts tokens), mcp_config.example.json,
                     fake_server.py (offline stand-in for Jira, GitLab, Azure DevOps; fixtures/ holds its data),
                     reference-mcp/ (one-file MCP server + handshake + tests),
                     lvkit.md (optional .vi reader: what it did here, install offline, MCP entry)
templates/           spec.md, plan.md, tracker-item.json, deck-outline-example.json,
                     research-brief-example.json: the input shapes the tools accept
  host-harness/      C host-test harness (Makefile, hal_stub.c, harness.h, test_main.c) to copy onto your firmware
outputs/             where generated decks, briefs, and reports land (not committed)
```

## Prove it works (30 seconds, offline)

```bash
python tools/doctor.py                # is this laptop ready? (2 seconds, prints READY)
python tools/check_repo.py            # validates skills, links, content, runs every test
python tools/golden_path.py           # runs every workflow end to end, leaves proof in outputs/golden/
python tools/trace_matrix.py          # requirement -> hazard -> test -> tracker matrix (fails on gaps)
make -C example-system test           # firmware twins: Python + C
make -C templates/host-harness test   # host harness over the C firmware through stubbed hardware (58 checks)
python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv
python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv   # LabVIEW port vs recording
python example-system/real-vi/topic_filter.py --replay example-system/real-vi/cases.csv --out outputs/topic-filter-python.csv
python tools/bench_compare.py example-system/real-vi/cases.csv outputs/topic-filter-python.csv   # real-VI port vs the diagram reading
python tools/build_deck.py templates/deck-outline-example.json outputs/example-deck.html
python tools/export_pptx.py templates/deck-outline-example.json outputs/example-deck.pptx
```

Open `outputs/example-deck.html` in the browser preview to see a finished deck, or
`outputs/example-deck.pptx` in a PowerPoint-compatible viewer (checked with LibreOffice Impress).

Requirements: Python 3.10+. Optional: a C compiler and `make` for the C tests. No packages to install.

## Words you will see

- **SRS** requirements list; each row has an ID like `SN-REQ-020` and says how it is verified.
- **ICD** interface control document: pins, buses, message formats between parts.
- **ADR** architecture decision record: one page saying what was decided and why.
- **Hazard / FMEA table** what can fail, how bad, how likely, what mitigates it, which test proves it.
- **Twins** the same firmware written twice, in C and Python, sharing one test list.
- **PAT / API token** a personal access token; the credential you use instead of a password. Never paste one into chat.
- **MCP** a small program Devin can call for tools and data; here, a single Python file.
- **HAL** hardware abstraction layer: the thin set of functions (SPI, I2C, UART, GPIO, clock) between firmware logic and the chip. The host harness replaces it.
- **Host tests / host harness** the firmware compiled and tested on a laptop with the HAL stubbed; no board.
- **VI** a LabVIEW program (`.vi`, a binary). **TestStand** NI's test sequencer that calls VIs in order.
- **Recording** a CSV/TDMS of what the real rig produced on one run; the thing a port is proven against.
- **Golden vectors** input/output rows exported from a model; an implementation must reproduce them.

## Rules in one breath

Customer-neutral, synthetic data only, least privilege, read-only integrations by default, ask
before any network access, never paste a token into chat. Details: `AGENTS.md`, `SECURITY.md`.
