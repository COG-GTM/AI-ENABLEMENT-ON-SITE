# Devin Desktop workflow library

Ready-to-run workflows for Devin Desktop (Devin Local agent) in a Federal environment: research
briefs, executive decks (HTML and PPTX), embedded design artifacts, what-if part swaps, spec-driven and
test-driven development, architecture docs, bug/capability tracking, and connecting to your tools
(CLI, REST API, MCP). Everything runs offline against a synthetic reference system. No customer data.

This is a reference repository, not a product. Every skill is a procedure Devin follows; the
sensor node in `example-system/` is what it practises on. The last step of every workflow is
"now do this on my project".

## Start here (2 minutes)

1. Clone or fork this repository and open the folder in Devin Desktop.
2. Devin reads `AGENTS.md` automatically and finds the skills under `.devin/skills/`.
3. Paste these three prompts, in order:

```
Reference this repo. What can you do here? Run the checks and show me.
/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN
/exec-deck Design review deck for the imu-c + CAN change: verdict, budgets, hazards, open items
```

Two minutes later you have a readiness check, a go/no-go analysis with recomputed budgets, and a
leadership deck open in the preview. Chained prompts like these are **workflows**; the five we ship
are in `WORKFLOWS.md`. Showing this to a room? Follow `WALKTHROUGH.md`.

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
| Mimic on your code | `Mimic the /design-artifacts workflow on my project in ../my-firmware` |

## The workflows

A skill does one job. A workflow chains skills so each stage's output file is the next stage's
input. Full tables with every prompt are in `WORKFLOWS.md`; here is what each one is for.

| # | Workflow | Skills in order | The question it answers |
| --- | --- | --- | --- |
| 1 | Design change to leadership brief | what-if-part-swap, design-artifacts, tdd, track-and-report, exec-deck | "What if we change this part, and what do I tell the review board?" |
| 2 | Research to decision | research-brief, exec-deck | "What do we know, with sources, and what is the recommendation?" |
| 3 | Feature: spec to tests to code to document | spec-driven, tdd, architecture-doc | "Add this feature properly, with the paperwork kept honest." |
| 4 | Connect a tool, then report | connect-tools, track-and-report, exec-deck | "Pull our real issues, read-only, and turn them into a status deck." |
| 5 | Stand up an MCP server by hand | mcp-server | "Show me the whole MCP protocol in one file, then add a tool to it." |

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

## Where things live

```
AGENTS.md            Devin reads this first: rules + which skill to use for what (under 40 lines)
WORKFLOWS.md         the 5 pipelines above, with every prompt and what each stage leaves behind
WALKTHROUGH.md       25-minute speaker path for showing the repo live, with a recovery move per beat
SECURITY.md          data-handling and least-privilege rules
.devin/skills/       one folder per skill, one SKILL.md each (cap: 12); open one to see the procedure
.devin/mcp_config.json  registers the offline reference MCP server
example-system/      the synthetic battery sensor node everything practises on
  docs/              SRS.md (requirements), ICD.md (interfaces), HAZARDS.md (FMEA), ADR-*.md (decisions),
                     POWER-BUDGET.md, TIMING.md, ARCHITECTURE.md
  parts/             one JSON per part (mcu-m0, imu-a/b/c, temp-x, can-xcvr): the numbers what-if uses
  src/               C firmware: node.c, packet.c, filter.c (host-buildable, hardware via callbacks)
  sim/sensor_node/   Python twin of the same firmware
  tests/             test_node.py, test_packet.py, test_filter.py, test_firmware.c
  tracker.json       bugs (SN-BUG-*) and capabilities (SN-CAP-*) linked to requirement and hazard IDs
  Makefile           make test runs both twins
specs/               001-diagnostics-packet/: a finished spec -> plan -> tasks example
tools/               small Python scripts the skills call. Standard library only.
  doctor.py          is this laptop ready?              check_repo.py    validates the whole repo
  what_if.py         power/timing recompute              trace_matrix.py  requirement -> hazard -> test -> tracker
  build_deck.py      JSON outline -> HTML deck           export_pptx.py   same outline -> PPTX
  research_brief.py  research JSON -> MD + HTML brief    tracker_report.py status report
  golden_path.py     runs every workflow end to end      tests/           tests for the tools
integrations/        README.md (which lane, which credential), curl-recipes.md, cli-recipes.md,
                     rest_client.py (read-only, redacts tokens), mcp_config.example.json,
                     reference-mcp/ (one-file MCP server + handshake + tests)
templates/           spec.md, plan.md, tracker-item.json, deck-outline-example.json,
                     research-brief-example.json: the input shapes the tools accept
outputs/             where generated decks, briefs, and reports land (not committed)
```

## Prove it works (30 seconds, offline)

```bash
python tools/doctor.py                # is this laptop ready? (2 seconds, prints READY)
python tools/check_repo.py            # validates skills, links, content, runs every test
python tools/golden_path.py           # runs every workflow end to end, leaves proof in outputs/golden/
python tools/trace_matrix.py          # requirement -> hazard -> test -> tracker matrix (fails on gaps)
make -C example-system test           # firmware twins: Python + C
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

## Rules in one breath

Customer-neutral, synthetic data only, least privilege, read-only integrations by default, ask
before any network access, never paste a token into chat. Details: `AGENTS.md`, `SECURITY.md`.
