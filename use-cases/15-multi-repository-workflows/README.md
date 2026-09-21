# Multi-Repository Workflows

## Outcome

Analyze a change that spans multiple synthetic repositories and produce a coordinated, dependency-aware implementation and validation plan.

## Candidate demo

- Map contracts and version dependencies.
- Identify change order and compatibility windows.
- Plan repository-specific diffs and tests.
- Define integration evidence and rollback.
- Execute only one bounded synthetic slice if approved.

## Evidence

The plan names affected interfaces, sequencing, compatibility tests, and ownership by role.

## Guardrails

Add each workspace explicitly. Do not grant broad directory access, mix unrelated repositories, push changes, or assume cross-repository write approval.
