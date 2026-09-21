# Demonstration Guardrails

## Always

- Use the approved Federal deployment and identity.
- Keep the workspace limited to reviewed synthetic material.
- Start with least privilege and explicit approvals.
- Show the plan, commands, diff, tests, and human decision points.
- Validate output independently.
- Stop on ambiguity involving data, access, network, or production impact.

## Never

- Add a real customer name, participant name, site, program, system identifier, or endpoint.
- Paste secrets, regulated data, production logs, proprietary code, or internal documents.
- Connect an unapproved integration or use a commercial service as a workaround.
- Disable security controls, certificate checks, audit logging, branch protection, or approval prompts to unblock a demo.
- Run privileged, destructive, deployment, messaging, payment, or account-management actions.
- Present generated output as correct without review.

## Stop conditions

Stop the scenario immediately if:

- The active tenant, account, repository, or workspace is not the expected one.
- A prompt requests broader filesystem, network, or integration access than approved.
- Sensitive or identifying content appears.
- A command could affect production or another user's data.
- The operator cannot explain the action or its rollback.
- A compliance or product claim cannot be verified.
