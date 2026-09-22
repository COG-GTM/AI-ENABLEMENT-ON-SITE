# Real VIs through the LabVIEW lane: what held, what did not

Four real `.vi` files from a public LabVIEW project were pushed through `/labview-to-python` with nothing
but the binaries: no LabVIEW, no HTML export, no screenshots, no recording. This is the worst-case input
the skill accepts, tried on somebody else's code. The synthetic example in `example-system/bench/` shows
the method on a rig; this folder shows what happens on code we did not write.

**Source**: [LabVIEW-Open-Source/LV-MQTT-Broker](https://github.com/LabVIEW-Open-Source/LV-MQTT-Broker),
a native LabVIEW MQTT broker, Zero-Clause BSD licence, commit `01aa7848b707` (2024-01-14). The four
files, their upstream paths and sha256 are in `sources.json`; `inventory.py --check` verifies them.
Chosen because topic-filter matching is pure string logic with a public specification
([MQTT 3.1.1 section 4.7](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html#_Toc398718106))
and the project ships its own requirement tests as VIs, so expected outputs exist without running anything.

| File | What it is | Role here |
| --- | --- | --- |
| `Create TopicFilter.vi` | Validates a filter string, builds the `_TopicFilter` class object, sets one of six errors | Ported |
| `Evaluate.vi` | Does a topic name match this filter | Ported |
| `Test MQTT-4.7.1-2.vi` | The project's own requirement test for the wildcard that must be last | Source of the U2* expected rows |
| `Test MQTT-4.7.1-3.vi` | The project's own requirement test for the wildcard that fills one level | Source of the U3* expected rows |

## Three levels of evidence, and which one this is

| Level | Means | Here |
| --- | --- | --- |
| 1. Static inventory | Read the binary: signature, terminals, constants, structures, SubVI calls, unresolved primitives, a diagram drawing | **Done**, 4 of 4 files: `VI-INVENTORY.md` (generated) |
| 2. Specification-level reconstruction | Write the Python from the inventory; derive expected outputs from a spec or the project's own tests; compare row by row | **Done**: `topic_filter.py`, `cases.csv`, `bench_compare` PASS on 39 rows |
| 3. Runtime equivalence | Run the original VI, record its outputs, compare the port against the recording | **Not done.** Needs LabVIEW. Nothing below claims it |

The synthetic rig example is level 3 against a synthetic recording. This folder is level 2 against real
code. Both are needed to believe a port; only your bench can supply level 3 for your VIs.

## What lvkit gave us (level 1)

| Command | Result |
| --- | --- |
| `lvkit describe` | 4/4: connector pane with types (`TopicFilter in: MQTT Server.lvlib:_TopicFilter.lvclass`, `Match: TF`), every case frame and loop, all six error strings verbatim, the constants `+ # $ /`, the diagram comment "/ = byte 47 / + = byte 43 / # = byte 35", the test VIs' requirement text and their input strings |
| `lvkit render` | 4/4: SVG block diagrams; readable after rasterising, dense for `Create TopicFilter.vi` (nested loop in a 7-frame case) |
| `lvkit unresolved` | 4/4: named two primitives it does not model (`String Subset`, `String To Byte Array`) and, for each file, the SubVI it cannot map without the rest of the project (`Read Topic Filter.vi`, `Define Test.vi`) |
| `lvkit generate` | **Failed on 4 of 4** given the single file: the unmapped primitive stops `Create TopicFilter.vi` and both tests, the missing SubVI stops `Evaluate.vi`. Run inside the full project checkout, where the SubVIs are next to it, `Evaluate.vi` got further (5 AST files) and still ended with `error: 4`. No usable Python came out of the tool |

The verbatim `unresolved` and `generate` output for each file is at the end of its section in `VI-INVENTORY.md`.
So the port was written by a person reading the inventory and the drawing, which is exactly what the skill
says will happen. The tool is a good pair of eyes, not a converter.

## What the port proves (level 2)

`python example-system/real-vi/topic_filter.py --replay example-system/real-vi/cases.csv --out outputs/topic-filter-python.csv`
then `python tools/bench_compare.py example-system/real-vi/cases.csv outputs/topic-filter-python.csv`
gives PASS on all 10 columns, 39 rows:

- 9 rows (`U2a`-`U3e`) are the input strings and expected verdicts read out of the project's two
  requirement-test VIs. The port agrees with every one, including the two error codes they expect
  (55043 for `MQTT/+/Topic`, 55044 for `MQTT+`).
- 30 rows (`S01`-`S30`) are the examples from MQTT 3.1.1 section 4.7 plus derived edge cases (empty,
  null byte, 65535/65536 bytes, case sensitivity, `$SYS`, trailing separators). Their `valid`/`match`
  columns are what the diagram reading says the VI does; `spec_valid`/`spec_match` are what the
  specification says, derived independently and kept in separate columns so the two never blur.

The compare caught one mistake while building the table: `sport+` was first written down as error 55043;
the diagram gives 55044 (the byte before the final `+` is not `/`), the same path as the project's own
`MQTT+` case. The table was corrected to the diagram, not the code to the table.

## Finding: the project swaps the two wildcards relative to MQTT 3.1.1

MQTT 3.1.1 says `#` is the multi-level wildcard (must be last) and `+` is the single-level wildcard (any
level). At this commit, `Create TopicFilter.vi` enforces "must be last" on `+` and "whole level" on `#`,
and both requirement-test VIs use the same convention (`MQTT/+` is their multi-level example, `MQTT/#/Topic`
their single-level one). The code and its tests agree with each other and disagree with the specification.
The port reproduces the VI, not the spec, on purpose; `--spec-diff` lists every row where the two disagree
(12 rows: this swap plus the two differences below). Whether this
is a deliberate choice or a defect in that project is not ours to decide; it is the kind of thing a port
surfaces, and the report is where it goes.

Two further differences from the spec, also in the diagram and reproduced: `Evaluate.vi` compares only the
filter's levels, so `sport/tennis` matches `sport/tennis/player1` and `sport/+` matches `sport`; and a
leading `$` blocks any wildcard level, even after a literal `$SYS` level.

## Not proven, and how to prove it

| Unknown | Why it is unknown | What settles it |
| --- | --- | --- |
| The For Loop's stop condition in `Evaluate.vi` | The drawing shows a conditional terminal; "continue if true" is the reading that makes the project's own tests pass. The other reading compares only the first level | One run of the VI with `a/b` vs `a/c` |
| `Match Pattern` with pattern `+$` | Assumed to match a literal `+` at the end of the string | One run with `MQTT/+` and `MQTT+` |
| `Spreadsheet String To Array` on a trailing `/` or blank levels | Assumed verbatim split, no trimming | One run with `a/` and `a//b` |
| The DVR cache in the class object | Dropped in the port; it is an optimisation with no visible output | Nothing to prove unless a caller reads it |
| Anything under error-in = error | Both VIs have an error frame that passes through; not exercised | Not needed for the logic |

Each of these is a single recorded run on a machine with LabVIEW; `rig_recording.csv` in the bench example
shows the shape. Until then this port is a faithful reading of a diagram, not a verified replacement.

## Retain / wrap / port

| Part | Decision | Reason |
| --- | --- | --- |
| Topic-filter validation and matching | **Port** | Pure logic, spec exists, project tests recovered, 39/39 cases agree |
| The class object and DVR cache | **Port, simplified** | Two fields carry all observable behaviour |
| The rest of the broker (sockets, packets, sessions) | **Not attempted** | Out of scope for a wildcard-logic exercise; would need a recording of a live session |

Recommendation: the method survives contact with real VIs. Expect the tool to fail on generation and
succeed on inventory; expect to read drawings; expect the port to surface at least one place where the
code disagrees with its own specification. Budget one recorded run per assumption before declaring
equivalence.
