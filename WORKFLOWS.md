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

## Rules that hold across every workflow

- Numbers come from tools (`what_if.py`, `tracker_report.py`, `make test`), never typed by hand.
- Each stage names its input file explicitly so the next stage does not guess.
- Generated files go to `outputs/` (not committed) unless the stage edits the reference system itself.
- Finish any workflow with `python tools/check_repo.py`.
- To run a workflow on your own project: `Mimic workflow 1 on ../my-firmware; its docs are in ../my-firmware/docs`.
