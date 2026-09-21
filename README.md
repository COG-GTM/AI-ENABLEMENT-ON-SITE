# AI Enablement On Site

A reusable, customer-neutral workspace for planning and delivering FedRAMP-only AI engineering enablement with Devin Desktop and Devin CLI.

## Operating boundary

- Use only the organization-approved Federal deployment and approved integrations.
- Treat every tenant, endpoint, plugin, MCP server, and external service as out of scope until its authorization and approval are confirmed.
- Use synthetic or explicitly approved sanitized data for every demonstration.
- Do not store customer names, participant identities, credentials, proprietary artifacts, regulated data, or production data in this repository.
- Do not perform production changes or destructive operations during demonstrations.

This repository is an enablement kit, not evidence that a product, integration, workflow, or dataset is authorized for a particular environment.

## Intended outcomes

- Establish a safe and repeatable on-site engagement plan.
- Demonstrate practical Devin Desktop and Devin CLI workflows.
- Identify and prioritize high-value engineering use cases.
- Capture decisions, action items, evidence, and follow-up without customer-identifying content.
- Leave behind reusable templates for future sessions.

## Start here

1. Review the [engagement charter](docs/00-charter/charter.md).
2. Complete the [environment readiness checklist](docs/01-readiness/environment-checklist.md).
3. Confirm the [FedRAMP boundary](docs/03-security/fedramp-boundary.md) and [data-handling rules](docs/03-security/data-handling.md).
4. Select scenarios from the [use-case catalog](use-cases/README.md).
5. Build a session flow with the [demo script template](templates/demo-script.md).
6. Run the [preflight checklist](docs/02-demo/preflight-checklist.md).
7. Record sanitized notes in [notes](notes/README.md) and outcomes in [docs/04-outcomes](docs/04-outcomes/README.md).

## Repository map

| Path | Purpose |
| --- | --- |
| `docs/00-charter/` | Intent, outcomes, agenda, roles, and open questions |
| `docs/01-readiness/` | Environment, repository, access, and integration readiness |
| `docs/02-demo/` | Run of show, facilitator guidance, preflight, and fallback plans |
| `docs/03-security/` | FedRAMP boundary, data handling, approvals, and demo guardrails |
| `docs/04-outcomes/` | Scorecard, adoption roadmap, and follow-up |
| `use-cases/` | Broad catalog of reusable engineering scenarios |
| `demo-workspaces/` | Reserved locations for synthetic demo assets |
| `templates/` | Use-case, prompt, decision, demo, and session templates |
| `notes/` | Sanitized decisions, action items, parking lot, and session notes |
| `assets/` | Approved, sanitized diagrams and presentation assets |

## Working with Devin

- Open this repository as the only workspace unless another approved directory is explicitly required.
- Start in Plan or Normal mode and review proposed actions before allowing changes.
- Use `@` in Devin CLI to attach only the files needed for the current task.
- Prefer small, reviewable tasks with an explicit outcome, constraints, and verification command.
- Inspect every diff and validation result before accepting or committing changes.
- Do not use unrestricted permission modes for an on-site demonstration.

See [Devin Desktop and CLI facilitator guidance](docs/02-demo/facilitator-guide.md) for a safe demonstration sequence.

## Repository status

This initial scaffold contains no customer artifacts and no executable demo application. Add only synthetic examples that satisfy the repository rules in [AGENTS.md](AGENTS.md) and [SECURITY.md](SECURITY.md).
