# Workflow Automation

## Outcome

Automate a repetitive local engineering task with bounded inputs, clear approvals, idempotent behavior, and deterministic validation.

## Candidate demo

- Document the manual steps and decision points.
- Separate safe automation from required human approval.
- Implement a dry-run mode.
- Validate inputs, outputs, retries, and failure behavior.
- Demonstrate repeat execution without unintended changes.

## Evidence

Dry run is accurate, repeated runs are safe, errors are visible, and output is limited to the approved workspace.

## Guardrails

Do not send messages, open external tickets, change accounts, deploy, purchase, delete, or call a real API during the demonstration.
