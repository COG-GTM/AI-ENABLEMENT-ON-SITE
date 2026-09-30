# Use cases

One folder per migration lane a team would adopt end to end. Each folder has:

- `README.md`: why this lane exists, when to use it, the exact commands in order, what each step leaves behind, and what it does **not** prove.
- `deck.json`: the slide outline (numbers copied from the fixture runs in `outputs/golden/`, never typed from memory).
- `deck.html`: the deck built from that outline with `python tools/build_deck.py use-cases/<name>/deck.json use-cases/<name>/deck.html`. Self-contained, opens in any browser offline. `python tools/check_repo.py` rebuilds every deck and fails if a committed one is stale.

| Folder | Lane | Status |
| --- | --- | --- |
| `labview-estate/` | binary VIs -> extraction -> project-level dependency map -> migration plan -> one proven rig | fixture, scanner, skills, golden stage |
| `matlab-repository/` | hundreds of `.m` files -> interconnections -> repository map -> bounded packs -> one proven function | fixture, scanner, skills, golden stage |
| `c-cpp-firmware/` | C/C++ tree -> host-testable vs target-only -> HAL seam -> host harness -> behavioural twin | fixture, scanner, skills, golden stage |
| `reusable-pipeline/` | scan -> pack -> agent -> compare -> report, journaled and resumable; approaches compared; token control | tool, CI example, golden stage |
| `other-translations/` | Ada to C++, Fortran modernisation, MATLAB to/from C++ for embedded targets | discussion only: method, no fixture |
| `advanced-topics/` | model choice and token cost, writing `AGENTS.md`, Windows, remote containers, tool approval status | discussion only |

Read the top-level `README.md` first if this repository is new to you; `WORKFLOWS.md` holds the same lanes as
prompt-by-prompt tables (workflows 6 to 12).
