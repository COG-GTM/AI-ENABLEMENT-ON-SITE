# Devin Desktop workflow library

Ready-to-run workflows for Devin Desktop (Devin Local agent) in a Federal environment: research
briefs, executive HTML decks, embedded design artifacts, what-if part swaps, spec-driven and
test-driven development, architecture docs, bug/capability tracking, and connecting to your tools
(CLI, REST API, MCP). Everything runs offline against a synthetic reference system. No customer data.

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

## All prompts

| You want | Paste this |
| --- | --- |
| A tour | `/tour` or `Reference this repo. What can you do here? Run the checks and show me.` |
| Research | `/research-brief Should we swap IMU A for IMU B? --sources example-system/parts,example-system/docs` |
| Executive deck (HTML) | `/exec-deck Build a leadership deck on the sensor node: requirements, top hazards, power budget, open bugs` |
| Design artifacts | `/design-artifacts Add a requirement and hazard for low-battery shutdown at 3.0 V` |
| What-if a new chip | `/what-if-part-swap Replace the IMU with imu-c and move the uplink to CAN` |
| Spec first | `/spec-driven Add a diagnostics packet with reinit count and uptime` |
| Tests first | `/tdd Make the temperature fault flag stay set until two in-range readings` |
| Architecture doc | `/architecture-doc Document the sensor node firmware` |
| Bugs and status | `/track-and-report Show open high-severity items and make a status report` |
| Connect a tool | `/connect-tools I have a GitLab PAT; pull open issues for project 123 read-only` |
| MCP server by hand | `/mcp-server run-reference` then `/mcp-server new-tool return the timing budget` |
| Mimic on your code | `Mimic the /design-artifacts workflow on my project in ../my-firmware` |

Prompts can also be plain English; `AGENTS.md` maps phrases like "make me a deck" to the right skill.

## What is in the box

```
AGENTS.md            Devin reads this first: rules + which skill to use for what (under 40 lines)
WORKFLOWS.md         5 pipelines: which skills to run in what order, and what each stage leaves behind
WALKTHROUGH.md              25-minute speaker path for showing the repo live
.devin/skills/       one folder per skill, one SKILL.md each (cap: 12)
.devin/mcp_config.json  registers the offline reference MCP server
example-system/      synthetic battery sensor node: C firmware + Python twin, requirements, ICD,
                     ADRs, hazards, power/timing budgets, parts data, bug tracker, tests
tools/               small Python scripts the skills call (doctor, deck builder, research brief,
                     what-if, tracker report, repo checker). Standard library only.
integrations/        CLI, REST/curl, and MCP recipes for Jira, Confluence, GitLab, GitHub, Azure DevOps
templates/           spec / plan templates and example inputs for the tools
outputs/             where generated decks, briefs, and reports land (not committed)
```

## Prove it works (30 seconds, offline)

```bash
python tools/doctor.py                # is this laptop ready? (2 seconds, prints READY)
python tools/check_repo.py            # validates skills, links, content, runs every test
make -C example-system test           # firmware twins: Python + C
python tools/build_deck.py templates/deck-outline-example.json outputs/example-deck.html
```

Open `outputs/example-deck.html` in the browser preview to see a finished deck.

Requirements: Python 3.10+. Optional: a C compiler and `make` for the C tests. No packages to install.

## Rules in one breath

Customer-neutral, synthetic data only, least privilege, read-only integrations by default, ask
before any network access, never paste a token into chat. Details: `AGENTS.md`, `SECURITY.md`.
