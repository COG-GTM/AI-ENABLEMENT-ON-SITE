# CI/CD Troubleshooting

## Outcome

Explain a seeded pipeline failure, isolate the responsible change, and validate a minimal correction locally or in an isolated runner.

## Candidate demo

- Analyze fabricated logs and pipeline configuration.
- Reproduce the failure with an approved local command.
- Trace the error to source or environment assumptions.
- Correct the issue and add a preventive check.
- Summarize the cause and evidence.

## Evidence

The failure is reproducible, the correction is focused, and the same validation passes afterward.

## Guardrails

Do not access production runners, expose CI secrets, rerun external pipelines, change branch protection, or publish artifacts during the demo.
