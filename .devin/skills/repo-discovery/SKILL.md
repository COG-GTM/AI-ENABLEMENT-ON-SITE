---
name: repo-discovery
description: Repository-scale discovery for text-based estates - a tree of MATLAB .m files or a C/C++ firmware tree with hundreds or thousands of files. Inventory every file, build the candidate dependency graph (calls, includes, packages, classes, dynamic and unresolved names), classify each unit port / wrap / retain / unreadable with the evidence, write the repository map, and emit a tracker-shaped migration backlog plus one bounded prompt pack per unit so no later step needs the whole tree. Discovery only; /matlab-to-code and /bring-your-firmware do the work one unit at a time.
argument-hint: "<folder tree of .m files or C/C++ sources> [--lang matlab|c] [--name <label>] [--top N] [--budget <tokens per pack>]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

Repository discovery for: `$ARGUMENTS`.

## What this is and is not

`/matlab-to-code` moves **one** algorithm with evidence; `/bring-your-firmware` puts **one** firmware tree
under host test; `/vi-fleet-discovery` is this same job for LabVIEW binaries. None of them answers "we have
two thousand `.m` files (or a firmware repository with forty modules): what is in there, what depends on
what, which parts can move first, and how do we work through it without handing the whole tree to an agent
on every step?" This skill answers that, and only that. It reads; it never edits a source file, never
runs one, and never writes the target code. Its outputs are a spreadsheet, a graph, a repository map, a
backlog, and a folder of prompt packs, all derived by two standard-library scripts, never typed in.

Everything it says is **static candidate evidence**: names that appear in the text and matched a rule.
It does not run MATLAB, compile for the target, expand macros, evaluate `#if`, follow function pointers,
resolve C++ overloads or templates, or evaluate `eval`/`feval`/`str2func`. Every place it could not decide
is written down as `unresolved`, `ambiguous`, `dynamic`, or `indirect`, never guessed. The proof that a
unit moved correctly still comes one unit at a time from `tools/bench_compare.py` against vectors or a
recording, or from the host harness tests.

## Step 0 - Preflight (one minute)

1. Decide the language. `.m` files -> `--lang matlab` (`tools/m_fleet_scan.py`). `.c/.cc/.cpp/.h/.hpp` ->
   `--lang c` (`tools/c_fleet_scan.py`). A tree with both is two runs with two `--name`s. LabVIEW
   `.vi` files are `/vi-fleet-discovery`, not this skill.
2. Confirm the tree is a **copy** you may read. The scanners only read; `tools/pipeline_run.py` writes only
   under `outputs/`. Never point them at a share you were not given.
3. `python tools/doctor.py`. Nothing optional is needed. For C/C++, a `gcc` on the PATH lets the scanner
   cross-check its include graph with `gcc -MM` (the summary names the reader it used; without gcc the
   graph is still built from the text and says so). Pass the target's `-D`/`-I` flags with `--cflags`
   when the tree's headers need them, exactly as the tree's own Makefile does.

## Step 1 - Run the scan

```bash
python tools/m_fleet_scan.py <tree> --name <label> [--top 50]                      # MATLAB
python tools/c_fleet_scan.py <tree> --name <label> [--top 50] [--cflags=-DBOARD_REV_C]   # C/C++
```

Ask before running (`exec` permission). Each run leaves seven files in `outputs/` (infix `-m-` for MATLAB,
`-c-` for C/C++):

| File | What it is | Who reads it next |
| --- | --- | --- |
| `<label>-m-fleet-inventory.csv` / `<label>-c-fleet-inventory.csv` | One row per file: identity and hash, kind, signature or defined functions, what it calls (tree / built-in / toolbox-or-vendor / unresolved / dynamic), structures and nesting, callers, classification with reasons, complexity, priority, missing inputs | You, a spreadsheet |
| `...-fleet-summary.json` | Counts, classification histogram, toolboxes or vendor prefixes, the reader used, notes on what was not evaluated | `/exec-deck` (numbers), the report |
| `...-repo-map.md` | The repository-level description: shape, packages or build files, entry points with call trees, leaf-first migration order, toolbox or target-only boundaries, unresolved and dynamic names, what the map does not know | You; the agent that documents the estate starts here, not from the tree |
| `...-dependency-map.json` | Every file as a node; `call` / `include` / `ambiguous` edges; `external`, `unresolved`, `dynamic` or `indirect_calls`, `entry_points`, `cycles`, `leaf_first_order`; for C/C++ also `target_only`, `seam_candidates`, `include_check` | `tools/prompt_pack.py`, `/exec-deck` |
| `...-dependency-map.dot` | The same graph for Graphviz (`dot -Tsvg`), capped at `--dot-top` nodes; the JSON is complete | Anyone with Graphviz; otherwise the `.md` |
| `...-migration-backlog.json` | Top `--top` port/wrap units in `templates/tracker-item.json` shape | `python tools/tracker_report.py --file outputs/<label>-m-migration-backlog.json` |
| `...-migration-backlog.csv` | Same items, 12 tracker columns | `tools/tracker_import.py --from csv` into the team tracker |

Scale: text parsing, so thousands of files take seconds to a minute. Run it per repository or per
top-level folder (`--name` each run). One malformed or non-UTF-8 file costs one `unreadable` row (MATLAB) or
a best-effort row with a note (C/C++), never the run. Re-running with the same `--name` rewrites the
inventory but **merges** the backlog: a unit keeps its id, status, owner, and dates; new units get the next
id; dropped units are carried forward. A backlog that exists but cannot be parsed stops the scan;
fix it or pass `--fresh`.

## Step 2 - Read the inventory and the map

Classification rules, first match wins (catalogues at the top of each scanner):

| Class | MATLAB evidence (`m_fleet_scan.py`) | C/C++ evidence (`c_fleet_scan.py`) | What happens next |
| --- | --- | --- | --- |
| `unreadable` | file could not be decoded or parsed | file could not be read | Ask the owner; nothing else can be said |
| `retain` | graphics-only script (`figure`, `plot`, `uicontrol`, no outputs), Simulink-bound code, MEX with no source | ISR handlers, inline assembly, memory-mapped registers, startup code, linker symbols, files under `bsp/`/`startup/` | Stays where it is. Document the interface, no port work |
| `wrap` | toolbox calls (Signal Processing, Optimization, ...), workspace inputs, `load` of `.mat` state | includes a target-only header, vendor / third-party / RTOS calls, calls into a `retain` file | Call it through a boundary (toolbox equivalent or HAL stub); port the logic around it |
| `port` | everything else: pure functions, package functions, classes with resolved calls | host-testable logic: pure functions, parsers, filters, C++ classes and templates without hardware | `/matlab-to-code` or host harness + `/tdd` candidate |

Then read `outputs/<label>-…-repo-map.md` top to bottom: **entry points** and their call trees (what the
estate does, in dependency order), **leaf-first migration order** (shared utilities first so callers find a
proven replacement), **cycles** to port together, **external / toolbox / vendor boundaries** (each is one
decision, not one per caller), **dynamic and unresolved names** (each is a question for the owner), and for
C/C++ the **seam candidates**: functions in `retain`/`wrap` files that `port` files call, which is exactly
where the host-harness stub goes. `unresolved_names`, `dynamic_calls`, and `indirect_calls` in the summary
say how much of the graph is a guess the tool refused to make.

## Step 3 - Pick where to start, and bound the context

Open the backlog or sort the inventory by `priority` descending. The first ten `port` rows with many
callers and low complexity are the first sprint; a shared leaf retires work in every caller. Write it down
as `outputs/<label>-repo-report.md`: counts from the summary JSON, the top candidates with reasons, the
boundaries (toolboxes, vendor code, target-only files), what is missing (vectors, tests, `-D` flags), and
the sentence "classification is static candidate evidence; each unit is proven by `tools/bench_compare.py`
or host tests".

Then build the packs:

```bash
python tools/prompt_pack.py --map outputs/<label>-m-dependency-map.json --budget 8000
```

One Markdown file per backlog unit under `outputs/packs/<label>-m/`: the unit's facts, the standing task for
its language (which skill, which steps), a result contract, its own source, a bounded excerpt of each direct
dependency, its callers by name, its open questions from the scan, and the boundaries. `manifest.json` holds
bytes and estimated tokens per pack and for the whole tree, so "we never send the whole repository" is a
number. Sections shrink in a fixed order when a unit exceeds `--budget`; the contract and boundaries never
do. An agent working a unit gets **one pack**, not the tree.

## Step 4 - Hand off

- Per unit, from the pack: `/matlab-to-code <path to the .m> --target <c|python|both>` or, for C/C++,
  `/bring-your-firmware <tree>` once for the harness then `/tdd` per unit. Each writes its proof to the
  pack's results folder and a `result.json` (shape in the pack).
- Unattended, when the team wants the loop in a repo they own: `python tools/pipeline_run.py --lang <matlab|c>
  --tree <tree> --name <label>` runs scan -> pack -> agent -> compare -> report with a journal and `--resume`.
  Without `--agent-cmd` the agent stage is a **dry run** that records `skipped` and invents nothing;
  `.github/workflows/migration-scan.yml` is the CI example. See `use-cases/reusable-pipeline/README.md`.
- Backlog status: `/track-and-report` on the backlog JSON, or the pipeline's `<label>-backlog-status.json`.
- Leadership: `/exec-deck Migration readiness from outputs/<label>-…-fleet-summary.json and the repo report`.

## Worked examples (offline, ship with the repository)

```bash
python tools/m_fleet_scan.py example-system/matlab-repo --name matlab-repo     # 27 .m files: packages, classes, private/, dynamic calls
python tools/c_fleet_scan.py example-system/firmware-repo --name firmware-repo  # 30 C/C++ files: ISR, registers, linker script, C++ templates
python tools/m_fleet_scan.py --check && python tools/c_fleet_scan.py --check    # both fixtures scan to their expected/ folders
python tools/prompt_pack.py --map outputs/matlab-repo-m-dependency-map.json
```

`example-system/matlab-repo/README.md` and `example-system/firmware-repo/README.md` list every construct each
fixture was built to exercise and what the scanner does with it. `tools/golden_path.py` runs both scans and
the pipeline dry run and checks the counts.
