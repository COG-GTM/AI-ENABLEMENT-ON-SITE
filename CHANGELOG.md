# Changelog

All notable changes to this repository are documented in this file. Entries are
grouped by week and reference the pull request that merged each change.

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
