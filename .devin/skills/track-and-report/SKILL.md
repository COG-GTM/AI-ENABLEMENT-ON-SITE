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
Data: `example-system/tracker.json`. Schema: `templates/tracker-item.json`. Tools: `tools/tracker_report.py`, `tools/tracker_import.py`.
The tracker is deliberately a file in Git so it works offline and diffs in review. If the user has Jira,
GitLab, GitHub, or Azure DevOps approved, see `/connect-tools` to read from it; the import below brings the
export into this schema.

## Add an item

1. Next id: `SN-BUG-nnn` or `SN-CAP-nnn` (zero-padded, never reuse).
2. Fields: type (bug, defect, capability), title (<= 80 chars, states the problem or outcome),
   severity (low, medium, high, critical), status (open), component, requirements[], hazards[],
   opened (YYYY-MM-DD), closed (null), owner (a role, not a person), notes (what is known, how to reproduce).
3. Link: every bug links at least one requirement or hazard, or notes says why none applies.
4. Validate: `python tools/tracker_report.py` (exits non-zero with the exact field on error).

## Close or update an item

Set `status` to `closed` (or `in_review`), `closed` to the date, append to notes what fixed it and which
test proves it (`tests/test_node.py::test_...` or the C test name). Never delete items.

## Import from Jira, GitLab, Azure DevOps, or a CSV

```
python tools/tracker_import.py --from jira   --in outputs/export.json --out outputs/tracker.json
python tools/tracker_import.py --from csv    --in outputs/export.csv  --out outputs/tracker.json --merge example-system/tracker.json
python tools/tracker_report.py --file outputs/tracker.json
```
`--from` is one of `jira`, `gitlab`, `ado`, `csv`; the JSON is the vendor's list response (all pages fetched first).
Only a fixed set of fields is mapped, the rest is dropped, and an unknown status or priority stops the import
with the allowed set. Items get a `source` (`jira:SN-101`); `--merge` updates a matching item in place, so
running the same import twice changes nothing. To practice without a real tool, start `python integrations/fake_server.py`
and follow "Prove it offline" in `integrations/README.md`; the fixtures in `integrations/fixtures/` import directly too.

## Report

```
python tools/tracker_report.py              # console summary
python tools/tracker_report.py --markdown   # paste into a review doc
python tools/tracker_report.py --json       # feed to /exec-deck stats slide
```
Report contents: total / open / closed / won't fix, open by severity and component, top 5 open by severity, oldest
open. For a deck: use the JSON in a `stats` slide and a `table` slide of the top 5; source line
"tracker.json as of <date>".

## Rules

- Roles not people; synthetic titles; no program or customer identifiers.
- A capability that changes the ICD or a requirement gets an ADR (`/design-artifacts adr`).
- Severity is about consequence to the requirement or hazard, not about how annoying it is.
