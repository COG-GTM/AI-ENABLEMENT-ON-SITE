---
name: track-and-report
description: Track bugs, defects, and capabilities in a plain JSON tracker linked to requirements and hazards, and produce status reports (text, Markdown, JSON) for reviews and decks.
argument-hint: "[add bug|add capability|close ID|report|report --markdown]"
permissions:
  ask:
    - Write(**)
    - exec
triggers:
  - user
  - model
---

Tracker operations. Request: `$ARGUMENTS`.
Data: `example-system/tracker.json`. Schema: `templates/tracker-item.json`. Tool: `tools/tracker_report.py`.
The tracker is deliberately a file in Git so it works offline and diffs in review. If the user has Jira,
GitLab, GitHub, or Azure DevOps approved, see `/connect-tools` to read from or push to it instead.

## Add an item

1. Next id: `SN-BUG-nnn` or `SN-CAP-nnn` (zero-padded, never reuse).
2. Fields: type (bug, defect, capability), title (<= 80 chars, states the problem or outcome),
   severity (low, medium, high, critical), status (open), component, requirements[], hazards[],
   opened (YYYY-MM-DD), closed (null), owner (a role, not a person), notes (what is known, how to reproduce).
3. Link: every bug links at least one requirement or hazard, or notes says why none applies.
4. Validate: `python tools/tracker_report.py` (exits non-zero with the exact field on error).

## Close or update an item

Set `status` to `closed` (or `in-review`), `closed` to the date, append to notes what fixed it and which
test proves it (`tests/test_node.py::test_...` or the C test name). Never delete items.

## Report

```
python tools/tracker_report.py              # console summary
python tools/tracker_report.py --markdown   # paste into a review doc
python tools/tracker_report.py --json       # feed to /exec-deck stats slide
```
Report contents: total / open / closed, open by severity and component, top 5 open by severity, oldest
open. For a deck: use the JSON in a `stats` slide and a `table` slide of the top 5; source line
"tracker.json as of <date>".

## Rules

- Roles not people; synthetic titles; no program or customer identifiers.
- A capability that changes the ICD or a requirement gets an ADR (`/design-artifacts adr`).
- Severity is about consequence to the requirement or hazard, not about how annoying it is.
