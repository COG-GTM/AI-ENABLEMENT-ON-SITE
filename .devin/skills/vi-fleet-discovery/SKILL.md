---
name: vi-fleet-discovery
description: Inventory a whole folder tree of LabVIEW VIs (.vi, .lvproj, TestStand .seq) in one pass - count them, read each one with lvkit when it is installed, classify every VI as port / wrap / retain / unreadable with the evidence, score complexity, and emit a fleet CSV plus a prioritised migration backlog that /track-and-report can report on. Discovery only; /labview-to-python does the migration one rig at a time.
argument-hint: "<folder tree holding .vi / .lvproj / .seq files> [--name <label>] [--top N] [--jobs N]"
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

Fleet discovery for: `$ARGUMENTS`.

## What this is and is not

`/labview-to-python` moves **one** rig: inventory, retain / wrap / port, reconstruct, prove against a
recording. It cannot answer "we have a hundred thousand VIs, how many are there, what is in them, which can
leave LabVIEW first?" This skill answers that, and only that. It reads; it never edits a `.vi`, never runs
one, and never generates Python. Its output is a spreadsheet and a backlog, both derived by
`tools/vi_fleet_scan.py` from what the files and the optional `lvkit` reader said, never typed in.

A classification here is **static evidence**: the SubVIs, primitives, project targets, and file names that
matched a rule. It is a starting order for the work, not a proof that a VI can be ported. The proof still
comes one VI at a time from `tools/bench_compare.py` against a recording. The same discovery pattern for
text-based estates (MATLAB `.m` trees, C/C++ trees) is `/repo-discovery`; this skill is for LabVIEW files only.

## Step 0 - Preflight (one minute)

1. `python tools/doctor.py`. The "Optional tools" row says whether `lvkit` is installed.
   - Installed: every VI's connector pane, structures, SubVIs, unresolved primitives, health, and call
     graph are read. Note the version it prints; it goes in the report.
   - Not installed: the scan still runs and lists every file, but every VI without a name or project-file
     signal is `unreadable` with reason `lvkit absent`. Say so in the report; offer the offline wheel
     install in `integrations/lvkit.md` (an administrator downloads wheels once on a connected machine).
2. Confirm the tree is a **copy** you may read (the scanner only reads, but `lvkit index` writes a cache
   under the user's home directory, not into the tree). Never point it at a share you were not given.
3. Recordings, exported HTML documentation, and `.seq` files sitting beside the VIs are picked up
   automatically. If they live elsewhere, say so in the report; the `missing_inputs` column will otherwise
   report them missing.

## Step 1 - Run the scan

```bash
python tools/vi_fleet_scan.py <tree>                       # default: outputs/<folder-name>-fleet-inventory.csv ...
python tools/vi_fleet_scan.py <tree> --name lab-a --top 30  # label the run; 30 backlog items
python tools/vi_fleet_scan.py <tree> --limit 200            # smoke test a huge tree first
python tools/vi_fleet_scan.py <tree> --jobs 4               # parallel lvkit calls, after one serial run warmed the cache
```

Ask before running it (`exec` permission). It leaves seven files in `outputs/`:

| File | What it is | Who reads it next |
| --- | --- | --- |
| `<name>-fleet-inventory.csv` | One row per VI (columns below) | You, the engineer, a spreadsheet |
| `<name>-fleet-summary.json` | Counts, classification histogram, project targets, sequence files, reader version, notes | `/exec-deck` (numbers), the report |
| `<name>-project-map.md` | The project-level description: shape, `.lvproj` targets, sequence files, entry points with call trees, leaf-first migration order, external SubVIs by library, unresolved built-ins, what the map does not know | You; `/architecture-doc` and the agent that documents the estate start here, not from the whole tree |
| `<name>-dependency-map.json` | Every VI as a node; `subvi` / `ambiguous` / `project-member` / `sequence-call` edges; `external`, `unresolved`, `entry_points`, `cycles`, `leaf_first_order` | `tools/prompt_pack.py` (one bounded pack per VI), `/exec-deck` |
| `<name>-dependency-map.dot` | The same graph for Graphviz (`dot -Tsvg`), capped at `--dot-top` nodes; the JSON is complete | Anyone with Graphviz; otherwise read the `.md` |
| `<name>-migration-backlog.json` | Top `--top` port/wrap candidates in `templates/tracker-item.json` shape | `python tools/tracker_report.py --file outputs/<name>-migration-backlog.json` |
| `<name>-migration-backlog.csv` | Same items, 12 tracker columns | `python tools/tracker_import.py --from csv --in <it> --out t.json --merge <their tracker> --prefix <PREFIX>` |

Scale: about one second per VI with lvkit (two reader calls per file), so a 100 000-VI estate is a day of
machine time, not a demo. Run it per project folder or per lab (`--name` each run), start with `--limit`,
then `--jobs` once the first run has warmed lvkit's cache (lvkit 0.8.4 can fail on a cold cache when run in
parallel). One corrupt file costs one `unreadable` row, never the run. The `lvkit index` call covers the
nearest enclosing `.git`/`.lvkit` root, which may be larger than the tree; the summary note says how many
VIs it covered.

## Step 2 - Read the inventory

Columns, in order, and where each number comes from:

| Column | Source | Meaning |
| --- | --- | --- |
| `path`, `name`, `size_bytes`, `sha256` | file system | Identity; the hash lets a later run prove the file did not change |
| `reader` | `lvkit --version` | `lvkit 0.8.4`, `lvkit absent`, or `lvkit 0.8.4: error` for that file |
| `lv_version`, `lock_state`, `library` | `lvkit describe` | Saved-with version; `password_protected` means the diagram cannot be read |
| `connector_signature`, `inputs`, `outputs` | `describe` inputs/outputs | `(name: type, ...) -> (name: type, ...)`: the Python function signature to come |
| `subvi_count`, `subvis` | `describe` body, nodes whose name ends `.vi` | What this VI calls; a library prefix (`X.lvlib:`) tells you where it lives |
| `primitive_count` | `describe` body, every other node | Built-in operations: the maths and string handling that becomes Python |
| `unresolved_count`, `unresolved` | `lvkit unresolved` | Primitives and SubVI terminal layouts lvkit does not model; each is a manual read later |
| `structure_count`, `structures`, `max_nesting` | `describe` body scopes | `case:6;for:1`; deep nesting means the port needs a state machine, not straight-line code |
| `callers_count`, `impact_score` | `lvkit index` + `query` | How many VIs in the indexed project call this one; blank when the index step failed |
| `health` | `describe` health flags | `ok` or the flags LabVIEW itself raised (`bad_subvi_link`, ...) |
| `lvproj`, `target` | `.lvproj` XML | Which project file lists the VI and the target chain above it, outermost first (`RT Controller [RT CompactRIO] > Chassis [cRIO Chassis] > FPGA Target [FPGA Target]`); any RT/FPGA target in the chain means retain |
| `sequences` | text `.seq` files | Which TestStand sequences call this VI: a relative `VIPath` is resolved against the sequence's folder; a bare name or a path from another machine matches by name and is marked `(name match, ambiguous)` when several VIs share it. Binary `.seq` files are listed in the summary with the conversion note |
| `classification`, `reasons` | the rules below | One of `port`, `wrap`, `retain`, `unreadable`, and the evidence that decided it |
| `complexity` | formula in the script docstring | `primitives + 2*structures + 3*SubVIs + 5*unresolved + 2*nesting + terminals` |
| `priority` | formula in the script docstring | Higher = start sooner: many callers, a recording beside it, exported docs, low complexity |
| `missing_inputs` | siblings of the file | `recording` (a `<VI name>*.csv/.tdms/.tsv` beside the VI that is not the input side: `_samples`, `_input`, `_stimulus`, `_vectors` do not count), `exported docs` (`<VI name>*.html`), `readable diagram`, `unresolved-primitive count` (the `lvkit unresolved` call failed, so `unresolved_count` is blank and complexity is a lower bound): what to ask the owner for before porting |

Classification rules, applied in this order (first match wins), with the evidence catalogue in
`tools/vi_fleet_scan.py` (`RETAIN_SIGNALS`, `WRAP_SIGNALS`):

| Class | Evidence | What happens next |
| --- | --- | --- |
| `unreadable` | lvkit failed on the file, `password_protected`, no block diagram, or lvkit absent with no other signal | Ask for the HTML export or the password owner; nothing else can be said |
| `retain` | FPGA, NI-RIO, Real-Time, timed loop, RT FIFO, Scan Engine, DAQmx timing / sample clock, or the VI sits under an RT/FPGA target in a `.lvproj` | Stays in LabVIEW. Document why, no port work |
| `wrap` | DAQmx (other than timing), VISA, IVI, modular-instrument drivers, NI-XNET, Call Library Function, .NET/ActiveX, TestStand API, shared variables, fieldbus | Call the existing VI, `.exe`, or driver from Python; port the logic around it |
| `port` | Everything else: sequencing, maths, string and array handling, limits, file I/O, reporting | `/labview-to-python` candidate |

Evidence tagged `[file name only]` came from the path, not the diagram (the only evidence when lvkit is
absent). Treat it as a hint and say so.

## Step 2b - Read the project map (target-neutral)

`outputs/<name>-project-map.md` is the "how does this whole project hang together" answer, assembled from
the per-VI facts, never typed in. Read it top to bottom:

- **Entry points and call trees**: VIs nothing else in the tree calls, each with what it calls (in the tree),
  what it calls outside the tree (`external SubVIs`, grouped by `.lvlib`/`.lvclass`), and which primitives
  lvkit could not resolve. A SubVI file name shared by several VIs in the tree is an `ambiguous` edge, drawn
  red, never guessed.
- **Leaf-first migration order**: shared SubVIs first, callers after, so each unit's dependencies already
  have a proven replacement when its own recording is replayed. Cycles are listed to port together.
- **External SubVIs**: each library is one decision (target-side equivalent, wrapper, or reason to retain);
  the histogram of unresolved built-ins says which vi.lib functions the estate leans on most.

The map is **target-neutral**. It describes the LabVIEW project (dependencies, built-ins, targets, order);
the language each unit moves to - Python, C#, C++, or stays in LabVIEW - is a per-unit decision written in
the backlog notes. `/labview-to-python` is the lane this repository proves end to end; the map does not change
if the plan picks another target. The JSON next to it is what `tools/prompt_pack.py` reads to build one
bounded context package per VI (its own facts plus one hop of callers and callees), so the agent that
documents or migrates a unit never receives the whole tree.

## Step 3 - Pick where to start

Open the backlog, or sort the CSV by `priority` descending. The first ten `port` rows that also have a
recording (or whose owner can produce one) are the first sprint. Prefer VIs with many callers: porting one
shared utility VI retires work in every caller. Skip anything `unreadable` until the owner supplies the
export; skip `retain` entirely. Write the choice down:

`outputs/<name>-fleet-report.md`: counts from the summary JSON (VIs, projects, sequences, classification
histogram, reader version), the top candidates with their reasons, what is missing (recordings, exports,
passwords, binary `.seq` files to convert), and the sentence "classification is static evidence; each port
is proven by `tools/bench_compare.py` against a recording". No VI is called portable until that PASS exists.

## Step 4 - Hand off

- Backlog status: `/track-and-report` on `outputs/<name>-migration-backlog.json` (or merge the CSV into the
  team's tracker with `tools/tracker_import.py` so the items get their ids).
- Each candidate: `/labview-to-python <path to the .vi> <recording>` (add `lvkit render` output or the HTML
  export). When it finishes, set the tracker item to `in_review`, then `closed` when the compare passes.
- Leadership: `/exec-deck Migration readiness from outputs/<name>-fleet-summary.json and the fleet report`.
  Every number on a slide comes from the summary JSON or `tracker_report.py`.
- Re-run the scan after a sprint with the same `--name`. The inventory is rewritten (the `sha256` column shows
  which files changed) but the backlog is *merged*: a VI keeps its id, status, owner, and dates and only its
  title, severity, and notes are refreshed; a new VI gets the next unused id; an item whose VI dropped out of
  the top N or was re-classified is carried forward untouched. The summary `notes` say how many were kept, new,
  and carried. A backlog file that exists but cannot be parsed stops the scan (nothing is overwritten); fix it or
  pass `--fresh` to throw the old backlog away. Identity is the `path:` at the end of each item's notes,
  so keep it when you edit items. Backlog `component` is the owning library or top folder, slugged to the
  tracker's `^[a-z0-9_-]{1,32}$` rule (the full library name stays in the notes).

## Worked example (offline, ships with the repository)

`example-system/` holds four real VIs from a public open-source LabVIEW project (`real-vi/`, 0BSD, provenance in
`sources.json`), a synthetic project file that lists them under `My Computer` beside an empty RT/FPGA target
(`fleet/fleet.lvproj`), and a synthetic XML sequence that calls two of them (`fleet/bench-sequence.seq`).

```bash
python tools/vi_fleet_scan.py example-system --name demo-fleet
cat outputs/demo-fleet-project-map.md               # entry points, leaf-first order, external SubVIs, unresolved built-ins
python tools/tracker_report.py --file outputs/demo-fleet-migration-backlog.json
python tools/vi_fleet_scan.py --check            # the fixture scans to example-system/fleet/expected/
```

With lvkit 0.8.4: 4 VIs, all `port` (topic-filter maths and two test VIs), 2 unresolved primitives per
validation VI, `Create TopicFilter.vi` called by 2 others, every VI missing a recording. Without lvkit: the
same 4 rows, `unreadable` with reason `lvkit absent`, project and sequence columns still filled. Both
results are checked in as `example-system/fleet/expected/` and verified by `tools/golden_path.py`.
