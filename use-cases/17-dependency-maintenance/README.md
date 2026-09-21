# Dependency Maintenance

## Outcome

Assess and apply a bounded dependency update with compatibility analysis, lockfile review, tests, and rollback guidance.

## Candidate demo

- Identify usage and compatibility constraints.
- Review a prepared advisory or release-note fixture.
- Update one dependency in a synthetic repository.
- Inspect transitive and lockfile changes.
- Run tests and document residual risk.

## Evidence

The source and target versions are explicit, checks pass, unexpected transitive changes are reviewed, and rollback is clear.

## Guardrails

Use approved registries and prepared versions. Do not install from an unapproved source, execute package lifecycle scripts blindly, or expose private registry configuration.
