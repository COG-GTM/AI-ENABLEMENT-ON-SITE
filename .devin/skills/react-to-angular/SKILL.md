---
name: react-to-angular
description: Plan and migrate a React unit to Angular with a shared regression contract and reviewable evidence.
argument-hint: "[React tree or one unit]"
allowed-tools:
  - read
  - grep
  - glob
permissions:
  ask:
    - exec
    - Write(**)
triggers:
  - user
  - model
---

Migrate one unit at a time from `$ARGUMENTS`; this is a strangler-fig lane, not a bulk rewrite.

## Ask

In Desktop or CLI Ask mode, clarify the Angular target and prompt for:

- a leaf-first strangler-fig boundary;
- the dependency graph from `tools/react_fleet_scan.py`;
- the React-to-Angular concept map and any design choices the application owner must make;
- the unit-test, coverage, and shared Playwright regression loop.

Do not choose the team's design system or treat a lexical graph as an authoritative architecture.

## Plan

1. Use Plan mode and `/spec-driven` to write `specs/<nnn>-<slug>/{spec,plan,tasks}.md`.
2. Store the Plan-mode artifact under `~/.devin/plans/`; use `megaplan` when deeper planning and a
   clarifying question are useful. See the [Devin Local guide](https://docs.devin.ai/desktop/devin-local);
   confirm mode names, plan paths, and keyword behavior on your build.
3. Run `/plan-to-tracker` in dry-run mode, review the Jira payload, and ask before any external write.
4. Order the migration leaf-first using the graph and spec. Create a feature branch; never commit to `main`.

## Code

For each approved task:

1. Write the Angular unit test first using `/tdd`.
2. Migrate the smallest unit: React components to standalone Angular components; hooks, context, and
   service modules to injectable services or signal stores. Preserve the fixture's shared data and
   test-ID contract.
3. Run the Angular unit tests and `tools/coverage_gate.py` with an 80% changed-line threshold, then
   run the shared Playwright spec against both the React and Angular apps.
4. Run `/sonar-gate` when the team's approved analysis lane is available. Review failures; do not
   waive a gate to make the migration appear green.
5. Draft a conventional commit message for the developer to review. The developer owns the commit.

This is not a transpiler and does not decide design-system choices. A passing fixture proves only the
flows exercised by its tests, not equivalence for an adopting application.
