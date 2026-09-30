# Use case: a MATLAB repository, from interconnections to the first proven function

## Why

Translating one `.m` file is easy. A repository of hundreds or thousands is not, because the cost is in the
**interconnections**: which script calls which function, what lives in `+packages` and `@classes`, what is
resolved through `private/` folders and path order, which names are toolbox calls, which calls are dynamic
(`eval`, `feval`, `str2func`), and what nobody calls any more. This lane builds that map once, without a MATLAB
licence, then migrates one function at a time with a bounded pack so the whole codebase is never fed to an
agent on every step.

## When

- A tree of `.m` files with no current call graph or ownership map.
- You must decide what to port, in what order, and what to keep in MATLAB behind an interface.
- You want repeatable evidence (CSV, JSON, Markdown) a tracker can report on, not a one-off reading.

## What you need

- This repository, Python 3.10+, Devin Desktop. No MATLAB, no toolboxes, no network.
- Read-only access to the tree. For the migration step you need vectors: inputs and outputs recorded from the
  original (a CSV per function; `example-system/matlab-repo/moving_avg_rt_vectors.csv` is the pattern).

## Step by step (fixture shown; substitute your tree)

| # | Do | Leaves behind |
| --- | --- | --- |
| 1 | `/repo-discovery example-system/matlab-repo --lang matlab --name matlab-repo` (or `python tools/m_fleet_scan.py example-system/matlab-repo --name matlab-repo`) | `outputs/matlab-repo-m-fleet-inventory.csv`, `-m-fleet-summary.json`, `-m-repo-map.md`, `-m-dependency-map.json` + `.dot`, `-m-migration-backlog.json` + `.csv` |
| 2 | Read `outputs/matlab-repo-m-repo-map.md`: counts, entry points and call trees, toolbox and workspace boundaries, dynamic calls, shadowed built-ins, unresolved names, leaf-first order | the repository description (paste into `/architecture-doc` for prose) |
| 3 | `python tools/prompt_pack.py --map outputs/matlab-repo-m-dependency-map.json --budget 8000` | `outputs/packs/matlab-repo-m/<ID>.md`, `manifest.json` (bytes and estimated tokens per pack) |
| 4 | For the first leaf-first `port` unit: `/matlab-to-code <path from the pack> --target python` (or `c`, `both`) | `outputs/<name>-notes.md`, vectors CSV, code + tests, `outputs/<name>-compare.md` |
| 5 | `/track-and-report status of outputs/matlab-repo-m-migration-backlog.json` | tracker report; rescans keep ids and statuses |
| 6 | `/exec-deck Migration readiness from outputs/matlab-repo-m-fleet-summary.json` | leadership deck |

Unattended: `python tools/pipeline_run.py --lang matlab --tree example-system/matlab-repo --name matlab-repo`
runs steps 1 and 3 and writes a report (`use-cases/reusable-pipeline/`).

## What the fixture shows (numbers from `outputs/golden/REPORT.md`)

`example-system/matlab-repo/`: 27 `.m` files built to exercise what a repository scan meets: a `+sn` package
with sub-packages, an `@BatteryModel` class folder and a classdef file, `private/` helpers, scripts with local
functions, `eval` / `feval` / `str2func` / `cellfun`, toolbox calls (Signal Processing, Optimization), a shadowed
built-in, an unresolved name, tests with vectors, a graphics-only script, a legacy file, and a malformed file.

- 27 parsed, 0 unreadable; 4 scripts, 30 functions, 2 classes, 4 packages, 2 tests
- 23 call edges, 1 unresolved name, 4 dynamic calls, 2 toolboxes used, 0 cycles
- classification: port 24, wrap 2, retain 1; 24 backlog items
- `python tools/m_fleet_scan.py --check` compares a fresh scan with `expected/`

## How the scanner works

`tools/m_fleet_scan.py` is a lexical scanner (standard library only): it strips comments, strings, and transposes,
finds `function` signatures, `classdef`, package and private membership, candidate calls and function handles, then
resolves each name in MATLAB's order as far as static text allows: local function, private folder, tree function,
frozen core-MATLAB list, frozen toolbox lists. Duplicates are marked ambiguous, not guessed. It reports shadowing,
unresolved names, toolbox use, workspace inputs (scripts that read variables they never assign), and units with no
vectors or tests.

## What this does not prove

- Path order, runtime dispatch, and which toolboxes are installed are not evaluated; the graph is candidate evidence.
- `eval` and friends are listed as dynamic calls; what they call at runtime is unknown.
- Numeric behaviour is proven only by `/matlab-to-code` and `tools/bench_compare.py` on the owner's vectors
  (the fixture's `model-to-code` stage replays 26 vectors: Python 3/3 and C 3/3 columns exact).

## Skills and files

`.devin/skills/repo-discovery/SKILL.md`, `.devin/skills/matlab-to-code/SKILL.md`, `tools/m_fleet_scan.py`,
`tools/prompt_pack.py`, `tools/bench_compare.py`, `example-system/matlab-repo/`, `example-system/model/`,
`WORKFLOWS.md` sections 7 and 10.
