# Changelog

All notable changes to this repository are documented in this file. Entries are
grouped by week and reference the pull request that merged each change.

## Week of 2026-09-25 to 2026-10-02

### Features

- Add `/vi-fleet-discovery` and `tools/vi_fleet_scan.py`: a whole-tree LabVIEW inventory (`.vi`, `.lvproj`, TestStand `.seq`) that classifies every VI as port / wrap / retain / unreadable with evidence, scores complexity, merges rescans into a tracker-shaped migration backlog, and ships a `fleet` golden-path stage plus a 42-slide LabVIEW migration walkthrough deck ([#18](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/18))
- Add `integrations/tool-approval-status.md`: a 66-row FedRAMP Marketplace status table (Authorized / In Process / Not on Marketplace / Not applicable / Unknown) with dated evidence for every tool, service, and vendor product the repository recommends ([#19](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/19))
- Add a `flow` diagram slide type to `build_deck.py` / `export_pptx.py` (inline SVG and native PPTX shapes from one validated layout) and a 14-slide executive briefing deck with `TALK-TRACK.md` for the LabVIEW, C/C++, MATLAB, and pipeline workflows ([#20](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/20))
- Add `/repo-discovery` with repository-scale MATLAB (`m_fleet_scan.py`) and C/C++ (`c_fleet_scan.py`) scanners, a `--graph` dependency map for `vi_fleet_scan.py`, bounded per-unit prompt packs (`prompt_pack.py`), a journaled and resumable `scan -> pack -> agent -> compare -> report` pipeline (`pipeline_run.py`, dry run by default), a `migration-scan.yml` CI example, and six `use-cases/<lane>/` folders with READMEs and decks ([#21](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/21))

### Bug Fixes

- `pipeline_run.py` retires results whose prompt pack changed across the whole manifest (archiving evidence and marking the agent unit `stale`) so neither `--limit` nor `--from-stage compare` can reuse or report old proof; MATLAB dynamic-literal edges are only created for a whole-literal name or balanced call, and `leaf_first_order` orders callers of a cycle after it ([#21](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/21))

### Improvements

- Add the weekly changelog for 2026-09-18 to 2026-09-25 ([#17](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/17))
- `check_repo.py` now runs the demo-fleet scan and `tracker_report.py` before link checks, rebuilds every `use-cases/*/deck.json` and fails on a stale committed `deck.html`, and raises the skill cap (`MAX_SKILLS`) from 15 to 16; `golden_path.py` grows to 22 stages (`fleet`, `m-fleet`, `c-fleet`, `pipeline`, `host-harness`) ([#18](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/18)) ([#21](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/21))
- Cross-link `/repo-discovery` from `/matlab-to-code`, `/bring-your-firmware`, and `/vi-fleet-discovery`; add workflows 9-12 to `WORKFLOWS.md` and routing rows to `AGENTS.md`, `README.md`, and `CONTRIBUTING.md` ([#18](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/18)) ([#21](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/21))
- Add a required-controls bullet to `SECURITY.md` and a "Rules in one breath" link in `README.md` pointing at the tool approval status table ([#19](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/19))

### Breaking Changes

- None this week.

## Week of 2026-09-18 to 2026-09-25

### Features

- Rebuild the repository as a Devin Local workflow library: slash-command skills under `.devin/skills/`, a synthetic embedded reference system in `example-system/`, and templates for generated artifacts ([#1](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/1))
- Add a first-run `/tour`, multi-skill pipelines in `WORKFLOWS.md`, a `doctor` readiness check, a golden-path runner, and a traceability matrix ([#3](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/3))
- Add offline PPTX export of the executive deck outline ([#4](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/4))
- Add an offline fake tracker server with fixtures and a tracker importer for the track-and-report workflow ([#5](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/5))
- Add LabVIEW-to-Python, MATLAB-to-code, and bring-your-firmware lanes with worked examples ([#10](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/10))
- Run the LabVIEW lane end to end on four permissively licensed open-source VIs, recording inventory, hand port, comparison, and review evidence with `sources.json` provenance ([#12](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/12))
- Add an MCP hosting guide (laptop, shared-entry, team-hosted, vendor-hosted models) and environment-first MCP server setup that asks scoping questions before writing config ([#13](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/13))
- Add a 16-slide MCP briefing deck outline ([#15](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/15))
- Add a Jira on-prem / Data Center connection guide, a tested `jira-cli` walkthrough, and a self-hosted read-only Jira MCP server example ([#16](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/16))

### Bug Fixes

- Fix the clean-checkout CI failure and harden the repository tools after review ([#2](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/2))
- Size PPTX table rows from wrapped text and cap the number of wrapped lines per cell so tables no longer overflow slides ([#6](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/6))
- Estimate PPTX table wrapping from glyph widths rather than code points so proportional fonts wrap where PowerPoint does ([#9](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/9))
- Harden the LabVIEW lane and the LabVIEW/Python comparator after an offline audit ([#11](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/11))

### Improvements

- Explain every skill, workflow, and directory for first-time users in `README.md` ([#7](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/7))
- Explain how to get the repository files onto a local machine and close the remaining README review findings ([#8](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/8))

### Breaking Changes

- `doctor` now rejects a same-named MCP config override unless it repeats every key of the entry it overrides; partial overrides in `.devin/mcp_config.local.json` that previously passed must be copied in full ([#14](https://github.com/COG-GTM/AI-ENABLEMENT-ON-SITE/pull/14))
