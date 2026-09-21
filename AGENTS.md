# Project instructions for Devin

This repository is a library of ready-to-run workflows for Devin Desktop (Devin Local agent).
Procedures live in skills under `.devin/skills/`. Keep this file short; do not add procedures here.

## Pick the right skill

When the user's request matches a row, invoke that skill (or tell them the slash command to run).

| User says something like | Skill |
| --- | --- |
| research, analyze, brief, compare sources, "what do we know about" | `/research-brief` |
| deck, slides, presentation, executive summary, brief leadership | `/exec-deck` |
| requirements, ICD, interface, ADR, hazard, FMEA, power budget, design artifact | `/design-artifacts` |
| what if we swap / replace / add a chip, sensor, device, part | `/what-if-part-swap` |
| spec, specification, plan, tasks, spec-driven, "start a feature" | `/spec-driven` |
| test first, TDD, red-green, write tests before | `/tdd` |
| architecture doc, system overview, C4, arc42, document how this works | `/architecture-doc` |
| bugs, defects, capabilities, tracker, status report, burndown | `/track-and-report` |
| connect to Jira, GitLab, Confluence, GitHub, Azure DevOps; CLI, API, token, PAT | `/connect-tools` |
| MCP server, add a server by hand, expose a tool, mcp_config | `/mcp-server` |

If nothing matches, read `README.md` and ask one clarifying question.

## Rules

- Customer-neutral: never add organization, program, project, person, site, or system identifiers. Use the synthetic system in `example-system/`.
- Synthetic data only. Never add secrets, tokens, keys, PII, CUI, export-controlled, production, or proprietary data. Secrets come from environment variables only.
- Least privilege: prefer Plan mode for first runs; ask before network access, external integrations, or writes outside this repository.
- No destructive or real-world side effects during demonstrations (no deletes, deployments, external posts, ticket writes).
- Do not claim a service is inside a FedRAMP boundary unless the user's administrator confirmed it.
- Write generated results to `outputs/` unless the skill says otherwise. Keep changes small and show the diff before committing.
- Verify before declaring done: run `python tools/check_repo.py` after editing skills, templates, or docs.
