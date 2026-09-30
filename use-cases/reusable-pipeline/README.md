# Use case: a reusable, low-touch migration pipeline the team owns

## Why

"Convert this entire repository" fails in two ways: the agent is handed the whole tree on every step and runs out
of context or tokens, and nothing is left behind that a second engineer, a second program, or a CI job can pick up.
This lane turns discovery and migration into a pipeline a team owns in its own repository: **scan** the tree,
**pack** one bounded context file per unit, run an **agent** per pack (or not: the default is a dry run), **compare**
each result against evidence, **report**. Every stage is journaled and resumable, every unit's cost is visible before
anything runs, and no unit is called done without a proof file.

## When

- More than one program to migrate, or one large enough that a single session cannot hold it.
- Token budget is a constraint, and you need to see and cap it per unit.
- The work should run unattended (a background job, a CI runner) with a human deciding what "done" means.

## What you need

- This repository, Python 3.10+. The scanners and the runner are standard library only. No network.
- A tree the scanners understand: `--lang c`, `--lang matlab`, or `--lang labview` (lvkit optional).
- Optionally, a command that takes one pack and writes one result (`--agent-cmd`). Devin Desktop's CLI needs the
  Cognition backend, so agent execution is where the offline path stops; the pipeline still runs everything else.

## Step by step (fixture shown; substitute your tree)

| # | Do | Leaves behind |
| --- | --- | --- |
| 1 | `python tools/pipeline_run.py --lang c --tree example-system/firmware-repo --name firmware-repo` | `outputs/pipeline/firmware-repo/scan/` (the scanner's files), `packs/` (one per unit + `manifest.json`), `REPORT.md`, `state.json`, `journal.jsonl`, `firmware-repo-backlog-status.json`. Agent stage: **dry run**, every unit `skipped: no --agent-cmd (dry run)` |
| 2 | Read `REPORT.md`: counts, budget, packs over budget (0 on the fixture), per-unit status | what a run would cost and in what order it would proceed |
| 3 | Same command with `--resume` | stages whose inputs are unchanged are skipped (journal says `skipped ... --resume`); `--from-stage pack` forces a stage; `--until pack` stops early |
| 4 | Add `--agent-cmd "<cmd> {pack} {results} {id} {unit}"` (and `--limit 3` to start) | `results/<id>/result.json` per unit following the contract at the end of each pack; existing `done`/`blocked` results are kept |
| 5 | Optionally `--compare-cmd "<cmd> {id} {unit} {results}"`; without it the compare stage checks that every listed evidence file exists | per unit: `proven`, `evidence present`, `unproven`, `failed`, `blocked`, `no result` |
| 6 | `python tools/tracker_report.py --file outputs/pipeline/firmware-repo/firmware-repo-backlog-status.json` | backlog items with a passing comparison moved to `in_review`; nothing is ever moved to `closed` by a tool |
| 7 | In CI: `.github/workflows/migration-scan.yml` (manual with `lang`/`tree`/`name` inputs, or weekly) | the same folder as a build artifact |

`--task-file <md>` replaces the per-language task text in every pack; `--budget N` sets tokens per pack;
`--opened YYYY-MM-DD` fixes the backlog date so reruns are byte-identical.

## What the fixture shows (numbers from `outputs/golden/REPORT.md`)

- firmware-repo: 15 packs, largest 1615 tokens est., whole tree 4896 tokens est.; 0 packs over the 8000 budget.
- Agent stage dry run: 15 units skipped, no `result.json` written, no `results/` folder created.
- `--resume` skipped `scan` and `pack` (input hashes unchanged); 46 journal events across the two runs.
- On the MATLAB fixture: 24 packs, largest about 1715 tokens est. On the LabVIEW fixture with lvkit: 4 packs.
- `tools/tests/test_prompt_pack_and_pipeline.py` drives a fake agent that returns `done` with evidence, `done` without
  evidence, and `blocked`, and checks the pipeline reports them as proven, unproven, and blocked respectively.

## Controlling context and tokens

1. **Scan once, read files, not the tree.** Every later step reads `dependency-map.json` (facts) and one pack, never the source tree.
2. **One pack per unit, with a budget.** A pack holds the unit's source, its direct dependencies' signatures and relevant
   excerpts, its callers, the open questions (unresolved, dynamic, vendor, target-only), and the result contract.
   When the budget is exceeded, dependency excerpts shrink first, then source is truncated, and the pack says so.
3. **Leaf-first order.** Dependencies migrate before callers, so a caller's pack can refer to finished work instead of
   carrying it.
4. **Measure before running.** `manifest.json` lists bytes and estimated tokens per pack; `REPORT.md` sums them. Decide
   `--limit` and the budget from those numbers.
5. **Persist everything the agent learns** in `results/<id>/` (notes, vectors, compare output). The next unit's session
   reads files, not a transcript.
6. **Resume, do not restart.** Stage inputs are hashed; unchanged stages are skipped; `done` and `blocked` results survive.

## Approaches compared

| Approach | What it is | Strength | Weakness | Here |
| --- | --- | --- | --- | --- |
| Structured intermediate files | scanner output (CSV, JSON, DOT, Markdown) as the contract between steps | deterministic, diffable, tool-checkable, language-agnostic | only as good as the scanner; static | the base of everything: `tools/*_fleet_scan.py`, `prompt_pack.py` |
| Reference repository | a finished pair (original + target) the agent imitates | shows the house style and the proof pattern | drifts; one example rarely covers the estate | `example-system/src` + `sim/`, `example-system/model/`, `bench/` |
| Skill / playbook files | procedures in `.devin/skills/*/SKILL.md`, routed by `AGENTS.md` | repeatable, reviewable, the team owns and edits them | needs the agent runtime; text, not code | 16 skills; `/repo-discovery`, `/matlab-to-code`, `/bring-your-firmware`, `/labview-to-python` |
| Graph-style controlled flow (LangGraph-like) | explicit state machine: nodes, edges, checkpoints, retries | resumable, auditable, bounded per node | another framework and runtime to own; still needs a model behind each node | `tools/pipeline_run.py` is that state machine in 1 file of standard library: stages, hashes, journal, resume; nodes call any command |

Use all four together: files as the contract, a reference pair for style, skills for the per-unit procedure, the
runner for control. **What Devin adds over a general agent**: the skills and `AGENTS.md` are read automatically per
repository; the CLI works in the IDE against the working tree; Plan mode and least-privilege defaults; the
`tools/` here are plain Python so the pipeline does not depend on any agent to run its discovery, packing, comparison,
or reporting stages.

## What this does not prove

- The dry run proves the glue and the journal, not a migration. No agent ran during `tools/golden_path.py`.
- `done` in a `result.json` is a claim; `proven` requires a comparison command or the evidence files to exist.
- Unattended agent execution needs a runner with access to the agent backend; the offline path ends at the packs.

## Skills and files

`tools/pipeline_run.py`, `tools/prompt_pack.py`, `tools/tracker_report.py`, `.github/workflows/migration-scan.yml`,
`.devin/skills/repo-discovery/SKILL.md`, `tools/tests/test_prompt_pack_and_pipeline.py`, `WORKFLOWS.md` section 12.
