---
name: exec-deck
description: Turn design material (requirements, hazards, budgets, tracker, research brief) into a self-contained HTML executive deck with recomputed numbers.
argument-hint: "[topic or source paths] [--slides N] [--audience who]"
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

Build a short executive deck. Request: `$ARGUMENTS`.
Default source when none is given: `example-system/` (SRS, HAZARDS, POWER-BUDGET, tracker).

## Rules

- Numbers are computed, not typed. Run the tools and paste their output:
  `python tools/tracker_report.py --json`, `python tools/what_if.py --markdown`, `make -C example-system test`.
- One idea per slide, sentence-case titles, at most 6 bullets, a source line (`note`) on any slide with numbers.
- Default length: 8-10 slides. Order: title, where we stand (stats), requirements highlights,
  safety (top hazards), security or quality posture, the decision or trade (two-column pros/cons),
  asks for leadership, sources.
- No organization, program, person, or site names. Footer must say the content is synthetic when it is.
- The deck is plain HTML with no external assets, so it opens anywhere and prints to PDF with `P`.

## Steps

1. Read the sources. Write down the 3 messages leadership must leave with.
2. Draft the outline as JSON using `templates/deck-outline-example.json` as the shape
   (slide types: title, section, bullets, two-column, table, stats, bars, quote).
3. Save it to `outputs/<slug>.deck.json`.
4. Build and open:
   ```
   python tools/build_deck.py outputs/<slug>.deck.json outputs/<slug>.html
   ```
   Open `outputs/<slug>.html` in the preview. Arrow keys move; `P` prints.
5. Check every slide visually: nothing clipped, every number traceable to a tool output or file.
6. Report to the user: path, slide count, the 3 messages, and any number you could not source.

## Variants

- "Safety deck": lead with `example-system/docs/HAZARDS.md`; table slide of risk >= 6; open mitigations.
- "Status deck": lead with `tracker_report.py --json`; stats slide open/closed; table of top 5.
- "Design review": include ADR pros/cons as two-column slides.
- If the user wants PowerPoint, say so honestly: this repo produces HTML; the outline JSON can be
  handed to any pptx tool the user already has approved.
