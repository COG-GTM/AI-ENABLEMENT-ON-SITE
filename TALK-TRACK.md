# Talk track: "Three toolsets, one proven path" (one hour on site)

Deck: `templates/deck-exec-briefing.json` (14 slides). Preview `templates/deck-exec-briefing.html` in any browser,
or rebuild it offline: `python tools/build_deck.py templates/deck-exec-briefing.json outputs/deck-exec-briefing.html`
(`python tools/export_pptx.py ... .pptx` for PowerPoint). Arrow keys, space or a click advance; Home / End jump;
`P` opens the print dialog with one slide per page.

Timing: 50 minutes of slides, 10 minutes of questions. Every number on a slide is quoted from the printed output
of `python tools/golden_path.py`, `python tools/vi_fleet_scan.py example-system --name demo-fleet` (with `lvkit`
installed) or `make -C templates/host-harness test`; `tools/tests/test_flow_deck.py` fails if the deck and the
tools disagree. Run `python tools/doctor.py` and `python tools/golden_path.py` the evening before so the live
commands below are warm (the golden path takes a few minutes the first time; the harness compiles in seconds).

Dashed boxes on slides 3, 7 and 8 are designed and not merged (`m_fleet_scan.py`, `c_fleet_scan.py`,
`prompt_pack.py`, `pipeline_run.py`, `/repo-discovery`). Say so out loud; never demo them.

| # | Slide | Minutes | Running total |
| --- | --- | --- | --- |
| 1 | Title | 2 | 2 |
| 2 | Why we are here: the five asks | 4 | 6 |
| 3 | The factory: every lane has the same shape | 6 | 12 |
| 4 | LabVIEW estate: from a folder of VIs to a proven rig | 6 | 18 |
| 5 | What the shipped LabVIEW rehearsal proves today | 4 | 22 |
| 6 | C/C++ firmware: host tests plus a Python twin | 5 | 27 |
| 7 | MATLAB / Simulink: model to C and Python | 5 | 32 |
| 8 | Reusable pipeline: files in, one prompt per unit, proof in CI | 4 | 36 |
| 9 | The evidence boundary | 3 | 39 |
| 10 | Retain, wrap or port | 3 | 42 |
| 11 | What Devin with this repository adds | 2 | 44 |
| 12 | What is not covered | 3 | 47 |
| 13 | Day one on your tree | 2 | 49 |
| 14 | Close | 1 | 50 |
| | Questions | 10 | 60 |

## 1. Title (2 min)

**Message:** Three toolsets, one shape: read the whole tree once, migrate one unit at a time, prove it with a comparison.

- Everything on the slides came out of tools in this folder; nothing was typed from memory.
- The reference system is synthetic and customer-neutral; the same commands run on your tree.
- Devin Desktop plus this repository is the whole footprint: offline, on a laptop.

Live (optional): `python tools/doctor.py` prints `READY` in a second; it shows the laptop is the demo.

## 2. Why we are here: the five asks (4 min)

**Message:** Each ask maps to a slide and to a file you can open afterwards.

- Repo-scale LabVIEW is slides 4 and 5; repo-scale MATLAB is slide 7 and is partly "next PR"; say that now.
- The low-touch pipeline is slide 8: the pattern exists and one scanner implements it; the other pieces are designed.
- Related examples: every lane ends in `example-system/` with a fixture, a port and a comparison.
- Advanced topics are slides 9 to 12, the boundaries; those are the slides that earn trust.

## 3. The factory: every lane has the same shape (6 min)

**Message:** One scan orders the work; one skill migrates one unit; one comparison closes it; the tracker and deck recompute.

- Read left to right: inputs are your files, read only. Discovery is static evidence and produces a backlog, not code.
- The middle is the skill that works on one unit; the blue gate is runtime proof, PASS or FAIL per column.
- The last column never invents numbers: `/track-and-report` reads the backlog, `/exec-deck` recomputes from files.
- The dashed model-tree scan is designed and not merged; the LabVIEW scanner is the shape it will copy.

Live (optional): `python tools/vi_fleet_scan.py example-system --name demo-fleet` writes the backlog in under a minute.

## 4. LabVIEW estate: from a folder of VIs to a proven rig (6 min)

**Message:** A `.vi` is a proprietary binary; there is no converter. The scan says where to start; the recording says when a rig is done.

- `/vi-fleet-discovery` walks the tree, calls `lvkit describe` and `lvkit unresolved` per VI, and classifies each as
  port / wrap / retain / unreadable with complexity and priority. Without `lvkit` every VI is unreadable, honestly.
- `/labview-to-python` takes one rig from the backlog: inventory from the HTML export or screenshots, a retain / wrap / port
  answer per SubVI, then `rig.py` with instruments as callbacks.
- Proof is `rig.py --replay` on the rig's raw samples and `tools/bench_compare.py` against the rig's own recording.
- Fixtures to point at: `example-system/fleet`, `example-system/real-vi`, `example-system/bench`.

Live (optional): `python example-system/bench/rig.py --replay example-system/bench/rig_samples.csv --out outputs/rig-python.csv`
then `python tools/bench_compare.py example-system/bench/rig_recording.csv outputs/rig-python.csv`.

## 5. What the shipped LabVIEW rehearsal proves today (4 min)

**Message:** These four numbers are the golden path's own words; read them as evidence, including the FAIL.

- `4` VIs, `1 .lvproj`, `1 .seq`: `port 4` with `lvkit` installed, `unreadable 4` without it. Same tree, two honest answers.
- `9/9 columns match the VI recording`, `3 soak steps`, `verdicts PASS/PASS/FAIL`: the port reproduces the failing step too.
- `39 cases replayed`, `10/10 columns`: four real open-source VIs ported from the diagram reading; `12 rows differ from MQTT 3.1.1` is a
  finding the comparison surfaced and the review documents.
- Nobody ran the original real VIs, so that lane stops short of runtime proof; the bench rig has a recording and does not.

Live (if time, a few minutes): `python tools/golden_path.py`; point at the `labview-to-python`, `real-vi` and `fleet` lines.

## 6. C/C++ firmware: host tests plus a Python twin, not a converter (5 min)

**Message:** Your C compiles on a laptop against a stubbed HAL; the Python twin is a second implementation kept honest by shared tests.

- `/bring-your-firmware` maps the tree read-only (build, RTOS, HAL seam, pure logic), picks link-time stubs or callbacks, and
  stands up `templates/host-harness` (`hal_stub.c`, `test_main.c`). Already on GoogleTest, Unity or Ceedling? It uses yours.
- `make test` runs nominal, injected-fault and boundary cases; on the example it prints `host tests: 58 checks passed`.
- `/tdd` adds the next behaviour to both twins (`example-system/src`, `example-system/sim`) from one test list.
- Say it plainly: nothing converts C to Python, and host tests do not prove target timing, interrupts or certification objectives.

Live (optional, seconds): `make -C templates/host-harness test`.

## 7. MATLAB / Simulink: model to C and Python that match the vectors (5 min)

**Message:** Write the numeric semantics down first, then make both twins reproduce the owner's vectors exactly.

- `/matlab-to-code` reads `.m` directly and `.slx` as ZIP plus XML; no MATLAB licence is needed on the laptop.
- The notes table (indexing, rounding, saturation, warm-up) exists before code; the vectors come from the model owner
  (`export_vectors.m` to `filter_vectors.csv`).
- Proof: `run_vectors.py` replays through the Python twin or the C via `vectors_driver.c`; `bench_compare.py` at tolerance 0 for
  integer outputs. The golden path prints `26 vectors replayed ... python 3/3 columns, c 3/3 columns match exactly`.
- The dashed repo-scale model scan (`m_fleet_scan.py`, `/repo-discovery`) is landing in the next PR; today the lane is one
  model at a time. Generated C from Embedded Coder is reviewed against the vectors, not replaced.

Live (optional): `python example-system/model/run_vectors.py --impl c --out outputs/model-c.csv` then
`python tools/bench_compare.py example-system/model/filter_vectors.csv outputs/model-c.csv --markdown`.

## 8. Reusable pipeline: files in, one bounded prompt per unit, proof in CI (4 min)

**Message:** Token use is bounded by files, not by prompts: scan once, write rows, give each unit one prompt carrying only its row.

- Solid boxes exist today: `tools/vi_fleet_scan.py`, its CSV / JSON / backlog, and `.github/workflows/check.yml`, which runs
  `check_repo.py` and `golden_path.py` offline on Python 3.10 and 3.12 and uploads `outputs/golden/` as the artifact.
- Dashed boxes are designed in the research plan and not merged: `m_fleet_scan.py`, `c_fleet_scan.py`, `prompt_pack.py`
  (dry-run by default) and `pipeline_run.py` (journaled, resumable).
- When they land, the golden path will stop at "prompt pack generated" and will not claim an agent ran.
- Nothing here needs a cloud service; the customer has Devin Desktop and this folder.

## 9. The evidence boundary (3 min)

**Message:** Static evidence orders the work; runtime evidence closes an item. Keep the two words apart.

- A fleet classification says how many and where to start; it never says a VI ports.
- A firmware map or a numeric-semantics table says where the seam is and which rules apply; it never says the code is correct.
- PASS from `bench_compare.py` says the port reproduces every column of one real run; host tests say the logic passes on a laptop.
- Every skill prints its own boundary in its output; a port without a recording is labelled a draft.

## 10. Retain, wrap or port (3 min)

**Message:** One answer per SubVI or block, with the reason written into the review; the goal is a bench you can trust, not zero LabVIEW.

- Port pure logic; wrap what works but cannot be re-verified cheaply or needs an NI driver you keep; retain FPGA, Real-Time and
  hardware-timed loops.
- Unreadable is an honest fourth answer: a backlog row asking for the export before anyone estimates.
- The fleet scanner proposes; the per-rig review decides. Sources: the two LabVIEW skills.

## 11. What Devin with this repository adds (2 min)

**Message:** The difference is not the model; it is the files, the gates and the printed boundaries around it.

- A general agent re-reads the tree every session and writes code that looks right; the proof is whatever you remember to ask for.
- Here the scanner reads once, each unit gets one bounded prompt, every lane ends in PASS or FAIL per column, and every skill prints
  what is not proven.
- Everything rebuilds offline from plain CSV and JSON anyone can open.

## 12. What is not covered (3 min)

**Message:** Read this slide slowly; it is the one that earns trust.

- No `.vi` to Python converter and no C to Python converter.
- Host tests do not prove target timing, interrupts, RTOS scheduling, DMA, power modes, MISRA or DO-178C objectives.
- Vector equivalence proves the code matches the model on those rows, not that the design is right.
- Repo-scale MATLAB and C scanners, the prompt pack and the pipeline runner are designed, not merged; no TestStand or TDMS file ships.

## 13. Day one on your tree (2 min)

**Message:** Seven commands, in this order, and the first backlog exists before lunch.

- `python tools/doctor.py`, then `python tools/golden_path.py` once to see every lane pass on the laptop.
- `python tools/vi_fleet_scan.py <your tree> --name <estate>` for the inventory and backlog; then one rig, one C tree, one model.
- `python tools/tracker_report.py --file outputs/<estate>-migration-backlog.json` is the first status report.

Live (optional): `python tools/tracker_report.py --file outputs/demo-fleet-migration-backlog.json` after the slide 3 scan.

## 14. Close (1 min)

**Message:** The recording, not the source, is the proof. Inventory says where to start; a comparison says when you are done.

- The ask: one rig with its recording, one firmware module, one model with vectors, this week.
- Leave the deck, `WORKFLOWS.md` and `templates/deck-labview-migration-walkthrough.json` (the long hand-out) with them.

## Questions (10 min)

Likely ones and where the answer lives: "Can it read our `.vi` files?" (`lvkit` gives inventory; the recording is the proof;
slide 4). "Does it replace Embedded Coder?" (no; it reviews generated C against the vectors; slide 7). "What runs in the cloud?"
(nothing on these slides; slide 11). "When do the scanners for MATLAB and C land?" (designed, not merged; slide 8).
