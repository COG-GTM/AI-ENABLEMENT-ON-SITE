---
name: spec-driven
description: Spec-driven development - write a specification, then a plan, then tasks, then implement task by task with tests, keeping the spec as the source of truth.
argument-hint: "[feature description] | plan | tasks | implement"
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

Spec-driven development for: `$ARGUMENTS`.
Four stages. Stop after each stage and show the user the file before moving on. Work happens in
`specs/<nnn>-<slug>/`. A finished example to copy the shape from: `specs/001-diagnostics-packet/`.

## Stage 1: specify (`spec.md`)

Copy `templates/spec.md`. Fill in: problem, users, user stories with acceptance criteria (given / when /
then), non-goals, constraints (memory, timing, power, security), open questions. Mark anything not
stated by the user as `[NEEDS CLARIFICATION]` and ask; never resolve it by guessing.
No implementation details in the spec.

## Stage 2: plan (`plan.md`)

Copy `templates/plan.md`. Fill in: approach, affected modules (file list), data and interface changes,
test strategy (which existing tests break, which new ones), risks, rollback. For firmware include the
requirement IDs touched and whether the ICD changes.

## Stage 3: tasks (`tasks.md`)

Ordered, small tasks (30-90 minutes each). Each: id, title, files, test that proves it, depends-on.
Tests-first ordering: the test task precedes the implementation task it verifies.

## Stage 4: implement

For each task in order: write or update the test, run it (must fail), implement, run it (must pass),
run the whole suite, tick the task in `tasks.md`. Commit per task with the task id in the message.
Stop and report if a task changes the spec; update `spec.md` first.

## Rules

- The spec wins. Code that disagrees with the spec is a bug in one of them; ask which.
- Keep artifacts short: spec under 2 pages, plan under 1, tasks under 20 items.
- Firmware in this repository: tests are `example-system/tests/` (Python) and `tests/test_firmware.c`;
  run `make -C example-system test`.

## Worked example

`/spec-driven Add a diagnostics packet with reinit count and uptime` produces
`specs/001-diagnostics-packet/{spec,plan,tasks}.md`; the plan touches ICD section 4 (new SYNC value),
`packet.c/.py`, `node.c/.py`, and adds golden-vector tests in both twins. This closes SN-BUG-004 / SN-CAP-005.
