---
name: research-brief
description: Research a question against local files (and approved web sources) and produce a one-page sourced brief in Markdown and HTML.
argument-hint: "[question] [--sources path,...] [--audience who]"
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

You are producing a decision-ready research brief. Question and options: `$ARGUMENTS`.
If no question was given, ask for one sentence: "What decision does this brief support?"

## Rules

- Every finding must cite a source id (S1, S2, ...). No source, no finding.
- Local files first: the repository, `example-system/`, anything the user points at.
- Web sources only if the user approves network access. When you use one, open it, confirm the page
  matches the claim, and set `"verified": true` on that source. Never invent or guess URLs.
- Rate each finding high / medium / low confidence. One idea per finding; at most 12 findings.
- Separate what the evidence shows from your interpretation. Unknowns go in `open_questions`.
- Author is a role ("analyst"), never a person. Do not add organization or program names.

## Steps

1. Restate the question in one sentence and name the audience.
2. Gather sources. For each: id, title, location (path or URL), date, type (repo, doc, web, data, interview).
3. Extract findings. Write each claim so it stands alone; attach source ids and confidence.
4. Write the bottom line (2-3 sentences), open questions, and next steps.
5. Save the structured file to `outputs/<slug>.research.json` using the shape in
   `templates/research-brief-example.json`.
6. Render:
   ```
   python tools/research_brief.py outputs/<slug>.research.json outputs/<slug>.md
   python tools/research_brief.py outputs/<slug>.research.json outputs/<slug>.html
   ```
   The tool rejects uncited claims, unverified URLs, and missing dates. Fix the JSON, not the tool.
7. Open the HTML in the preview, then summarise the bottom line to the user in 3 lines and list the
   open questions. Offer `/exec-deck` if leadership slides are wanted.

## Example

`/research-brief Should we swap IMU A for IMU B? --sources example-system/parts,example-system/docs`
produces outputs/imu-swap.research.json, .md, and .html with findings drawn from the part files,
POWER-BUDGET.md, and `python tools/what_if.py --imu imu-b`.
