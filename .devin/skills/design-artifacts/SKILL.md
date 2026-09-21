---
name: design-artifacts
description: Generate or update embedded-system design artifacts (requirements, ICD, ADR, hazard/FMEA table, power and timing budgets) with traceable IDs.
argument-hint: "[artifact: srs|icd|adr|hazards|power|timing|all] [subject]"
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

Produce embedded design artifacts. Request: `$ARGUMENTS`.
Reference examples live in `example-system/docs/`; copy their structure, not their content, when the
user has their own system. When no system is given, work on the sensor node.

## Artifact recipes

| Artifact | Template to copy | Must contain |
| --- | --- | --- |
| Requirements (SRS) | `example-system/docs/SRS.md` | ID per line (`XX-REQ-nnn`), shall-statement, verification column (test, analysis, inspection) |
| Interface control (ICD) | `example-system/docs/ICD.md` | Electrical, per-bus parameters, byte-level message table, CRC definition, one worked vector |
| Architecture decision (ADR) | `example-system/docs/ADR-0001.md` | Context, decision, alternatives table with pros/cons, consequences, linked requirement IDs |
| Hazard / FMEA | `example-system/docs/HAZARDS.md` | Failure mode, effect, severity, likelihood, risk, mitigation, verified-by, status |
| Power budget | `example-system/docs/POWER-BUDGET.md` | Per-consumer active current, duty, average; total vs limit; life estimate; method |
| Timing budget | `example-system/docs/TIMING.md` | Per-step worst case, total vs period, what would change it |

## Rules

- Every requirement, hazard, and tracker item gets a stable ID. Never renumber existing IDs.
- Every hazard with risk >= 8 must point at a requirement and a test or analysis.
- Numbers come from part data (`example-system/parts/*.json`) or the user's data sheets; if a number is
  assumed, mark it "assumed" in the table.
- Keep each artifact to one file, one screen of tables where possible. Prose goes in ADRs.
- Synthetic only: no real part numbers, vendors, programs, or organizations unless the user supplies them
  for their own private repository.

## Steps

1. Confirm which artifact(s) and which system. If the system is new, ask for: interfaces, sample rates,
   power source and life target, and the top 3 things that must not fail.
2. Read the matching template and any existing artifacts to keep IDs consistent.
3. Write the artifact into `example-system/docs/` (or the user's `docs/`).
4. Cross-link: new requirements referenced from ICD/ADR/HAZARDS where relevant; new hazards into
   `tracker.json` if mitigation is open (use `/track-and-report`).
5. Run `python tools/check_repo.py`; fix link and ID issues.
6. Summarise: what was created, IDs added, open items. Offer `/exec-deck` for a review deck.
