# Use-Case Catalog

Use this catalog to select a small number of scenarios that match the audience while remaining synthetic, isolated, and verifiable.

| ID | Category | Example evidence |
| --- | --- | --- |
| 01 | [Codebase understanding](01-codebase-understanding/README.md) | File-cited architecture and code-path map |
| 02 | [Feature development](02-feature-development/README.md) | Reviewed plan, focused diff, passing tests |
| 03 | [Debugging and root cause](03-debugging-and-root-cause/README.md) | Reproduction, cause, regression test, fix |
| 04 | [Test generation and quality](04-test-generation-and-quality/README.md) | Meaningful tests and coverage rationale |
| 05 | [Refactoring](05-refactoring/README.md) | Behavior-preserving diff and passing tests |
| 06 | [Legacy modernization](06-legacy-modernization/README.md) | Incremental migration plan and compatibility evidence |
| 07 | [Documentation and knowledge transfer](07-documentation-and-knowledge-transfer/README.md) | Source-grounded documentation |
| 08 | [Developer onboarding](08-developer-onboarding/README.md) | Verified setup and first-task guide |
| 09 | [Code review](09-code-review/README.md) | Prioritized findings with file references |
| 10 | [Security and compliance](10-security-and-compliance/README.md) | Defensive findings and control evidence |
| 11 | [CI/CD troubleshooting](11-ci-cd-troubleshooting/README.md) | Failure explanation and validated correction |
| 12 | [Infrastructure as code](12-infrastructure-as-code/README.md) | Static validation and safe change analysis |
| 13 | [Data analysis and automation](13-data-analysis-and-automation/README.md) | Validated synthetic transformation |
| 14 | [Requirements to implementation](14-requirements-to-implementation/README.md) | Traceable acceptance criteria and plan |
| 15 | [Multi-repository workflows](15-multi-repository-workflows/README.md) | Coordinated, scoped change plan |
| 16 | [Performance optimization](16-performance-optimization/README.md) | Reproducible before-and-after measurement |
| 17 | [Dependency maintenance](17-dependency-maintenance/README.md) | Compatibility analysis and passing checks |
| 18 | [Incident analysis](18-incident-analysis/README.md) | Timeline and hypotheses from fabricated evidence |
| 19 | [Accessibility and user experience](19-accessibility-and-user-experience/README.md) | Standards-based findings and tests |
| 20 | [Workflow automation](20-workflow-automation/README.md) | Safe, local, idempotent automation |

## Selection method

1. Copy `templates/use-case-plan.md`.
2. Define one observable outcome and deterministic evidence.
3. Confirm the Federal, data, repository, network, and integration boundaries.
4. Prefer a read-only first scenario, then a small reversible change.
5. Prepare an offline fallback.
6. Rehearse with the exact approved tools and synthetic assets.

A category is not approval to use real workflow data. Recreate the relevant shape with synthetic material.
