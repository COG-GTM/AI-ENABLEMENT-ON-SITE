# Use case (discussion only): Ada to C++, Fortran modernisation, MATLAB to/from C++ for embedded targets

**Status: no fixture, no scanner, no skill for these three.** They came up as related examples. What follows is how
the same method applies, what the tooling landscape looks like, and what would have to be built before any of it
counts as a demonstrated lane. Nothing here should be presented as hands-on capability.

## The method is the same

Every lane in this repository has the same four stages, and none of them is language-specific in principle:

1. **Discover**: inventory the tree, build the candidate dependency graph, mark what is dynamic, vendor, or target-only,
   classify `port / wrap / retain / unreadable` with reasons, write a repository map and a backlog
   (`tools/*_fleet_scan.py`, `/repo-discovery`, `/vi-fleet-discovery`).
2. **Pack**: one bounded context file per unit, leaf-first, with a result contract (`tools/prompt_pack.py`).
3. **Migrate one unit** with a skill that ends in a comparison against the original's behaviour on recorded vectors
   (`tools/bench_compare.py`).
4. **Track and report** (`/track-and-report`, `/exec-deck`), rescanning as the estate changes.

To add a language you write the scanner (a `*_fleet_scan.py` that emits the same `dependency-map.json` shape), a
fixture under `example-system/`, an `expected/` folder and `--check`, a golden stage, and either extend an existing skill
or add one (cap 16, `CONTRIBUTING.md`). `tools/prompt_pack.py` and `tools/pipeline_run.py` then work unchanged.

## Ada to C++

- Why teams ask: Ada toolchain availability and staffing; C++ is where the rest of the embedded stack lives.
- What makes it hard: Ada's type system (ranges, subtypes, discriminated records), tasking and protected objects,
  generics, representation clauses, SPARK contracts; safety-critical certification evidence tied to the original.
- Tooling landscape (verify status and licences with your administrator before use; see
  `integrations/tool-approval-status.md`): GNAT and `libadalang` (AdaCore, GPL/Community and Pro editions) can parse Ada
  and expose a full syntax tree from Python; AdaCore's GNAT Pro Common Code Generator produces C from Ada as a
  supported product; there is no maintained open-source Ada-to-C++ translator.
- Discovery that is realistic here: a lexical scanner for `with`/`use` dependencies, package specs vs bodies, tasks,
  protected types, generics, representation clauses, pragmas, and `Interfaces.C` bindings. Per-unit classification
  would mark tasking, representation clauses, and interrupt handlers `retain` or `wrap` first.
- Proof: the same recorded-vector comparison per subprogram; certification artefacts need a separate, human-owned plan.

## Fortran modernisation

- Why teams ask: numerical codes in fixed-form Fortran 77 with COMMON blocks, EQUIVALENCE, computed GOTO, implicit
  typing; the goal is usually modern Fortran (modules, explicit interfaces, allocatable arrays) or C++ / Python bindings,
  rarely a full rewrite.
- What makes it hard: implicit typing and COMMON make the dependency graph a data-flow problem, not a call graph;
  numerics (precision, evaluation order, compiler flags) decide whether "equivalent" is even well-defined.
- Tooling landscape (verify before use): `fparser` (Python, BSD, parses fixed and free form), LFortran (compiler with
  an AST/ASR you can inspect; BSD), `fable`/`cctbx` (Fortran to C++ converter, BSD, aimed at a specific numerical
  style). `f2py` (NumPy) wraps Fortran for Python rather than translating it - often the right first step.
- Discovery that is realistic here: a scanner for program units, `CALL` / function references, COMMON and MODULE
  membership, `INCLUDE` files, implicit typing, `EQUIVALENCE`, computed/assigned GOTO, and I/O units. Classification:
  COMMON-heavy and I/O-heavy units `wrap` first (keep them, expose an interface), pure numerical kernels `port`.
- Proof: vectors with explicit precision and tolerance per column (`tools/bench_compare.py` already supports both).

## MATLAB to/from C++ for algorithms that must run on embedded targets

- What exists here today: `/matlab-to-code --target c` (MATLAB function or Simulink model to C, proven on vectors;
  `example-system/model/` runs 26 vectors through the Python and C twins with exact match), `/repo-discovery` for the
  MATLAB tree, `/bring-your-firmware` and `templates/host-harness/` for the C side. That covers MATLAB to C on a host.
- What does not exist here: C++ output, MATLAB Coder / Embedded Coder review as a fixture (Coder needs a MathWorks
  licence; the skill describes reviewing generated code but no generated code is committed), fixed-point conversion,
  timing on a target, and the reverse direction (C++ algorithm to MATLAB for simulation).
- What is realistic to add: a `--target cpp` in `/matlab-to-code` (thin wrapper over the C path), a fixed-point
  vector set in the fixture, and a host-harness step that times the kernel with the target compiler's `-O` flags. The
  reverse direction is the C scanner plus a MATLAB emitter; nothing here starts it.

## Environment notes for a FedRAMP / CUI setting

- Everything in this repository runs offline from the working tree; the tools are standard-library Python plus an optional
  C compiler and optional `lvkit`.
- Viewing public repositories was confirmed for the intended environment; cloning was not. The README describes the
  Download-ZIP path; the tools above should be evaluated the same way, with your administrator's approval
  (`integrations/tool-approval-status.md`, `SECURITY.md`).

## Skills and files

`use-cases/reusable-pipeline/README.md` (how a new language plugs in), `tools/fleet_common.py` (shared graph code),
`tools/prompt_pack.py`, `.devin/skills/matlab-to-code/SKILL.md`, `CONTRIBUTING.md`.
