# Contributing

## Principles

Contributions must remain reusable, customer-neutral, synthetic, and appropriate for a FedRAMP-only enablement workflow.

## Workflow

1. Start from an issue or a documented use-case objective.
2. Create a focused branch from `main`.
3. Add or update the relevant template, use case, demo asset, or guidance.
4. Validate all commands and links that the change introduces.
5. Review the complete diff for identifying information, sensitive data, secrets, and unsupported compliance claims.
6. Open a pull request using the repository template.

## Acceptance criteria

- No customer, participant, program, site, or system identifiers
- No secrets, regulated information, production data, or proprietary artifacts
- Only synthetic or explicitly approved sanitized examples
- Clear prerequisites, guardrails, expected outcome, and validation evidence
- No dependency on an unapproved external service or integration
- No destructive or production-changing demonstration step

Do not commit personal overrides such as `AGENTS.local.md` or `.devin/config.local.json`.
