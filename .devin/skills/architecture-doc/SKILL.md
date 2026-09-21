---
name: architecture-doc
description: Write or refresh an architecture document (short arc42 / C4 style) derived from the actual code, with module table, runtime view, decisions, and risks.
argument-hint: "[path to system or module] [--level overview|detailed]"
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

Architecture documentation for: `$ARGUMENTS` (default: `example-system/`).
Model output: `example-system/docs/ARCHITECTURE.md`. Copy its section order.

## Rules

- Derive from code, not from memory: list modules by reading the file tree, public headers, and
  `__init__.py` exports. Every module row must name a real file.
- Diagrams are ASCII (context, containers, one runtime sequence). They must render in plain Markdown.
- Link, do not duplicate: point at ADRs, SRS, HAZARDS, and tests instead of restating them.
- Keep the overview to about 2 pages. Detailed level adds one section per module with its public API.
- State what is not decided or not known instead of filling it in.

## Sections (in order)

1. Purpose and constraints (3-5 lines, with requirement IDs).
2. Context diagram: external actors and interfaces.
3. Building blocks table: module, files (implementation and twin/test), responsibility.
4. Runtime view: the main loop or request path as a one-line-per-step sequence.
5. Key decisions: one line per ADR with a link.
6. Quality scenarios: requirement, how it is verified (test or analysis), evidence path.
7. Risks and technical debt: link HAZARDS and open tracker items (`python tools/tracker_report.py`).

## Steps

1. Inventory: `glob` the tree; read headers/`__init__` for public API; read tests for behaviour.
2. Draft the document; run `python tools/check_repo.py` to verify every path you cite exists.
3. Show the diff to the user. Offer `/exec-deck` to turn it into a review deck.
