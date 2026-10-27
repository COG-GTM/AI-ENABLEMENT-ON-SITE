---
name: test-backfill
description: Add characterization tests to legacy code safely, then gate changed lines on coverage.
argument-hint: "[code area or behavior] [--threshold 80]"
triggers:
  - user
  - model
---

Add tests to existing behavior in `$ARGUMENTS`. Keep production code unchanged during test
backfill unless the developer explicitly asks for an implementation change.

## Characterization tests

1. Map the selected behavior from its entry point to its dependencies. Find a seam at the narrowest
   stable boundary: an injected service, adapter, repository, clock, filesystem interface, or API
   client. Avoid replacing core behavior with a mock.
2. Start at leaves: deterministic pure functions and adapters, then module or API behavior, then
   smoke or end-to-end coverage where the cost is justified.
3. Record what the code does today, including awkward but relied-on behavior. Keep assertions about
   observable inputs, outputs, errors, and side effects.
4. Add one behavior at a time. Run its test, then the relevant suite after every commit-sized change.
5. Never weaken an assertion merely to turn a failing test green. If a test exposes a suspected real
   defect, record a tracker item for the owner and leave production code unchanged.

## Test layer selection

| Layer | Use it for |
| --- | --- |
| Unit | Pure functions, boundary conditions, formatting, and decision logic |
| API or component | Contracts, routing, persistence adapters, and interaction between modules |
| Smoke | A short check that the application starts and its critical path is reachable |
| End-to-end | A small number of high-value user journeys whose behavior crosses the full application |

Prefer the cheapest layer that proves the contract; add higher layers for risks that unit tests
cannot exercise. For a frontend change, start the app, visit its main pages, exercise the affected
flow, and save a screenshot or recording as evidence. If no runnable frontend is available, report
that limitation rather than implying it was checked.

## Net-new coverage gate

Run the project's normal coverage command first. Examples below are only examples; your project's
runner may differ:

```bash
ng test --watch=false --code-coverage
npx jest --coverage --coverageReporters=lcov
npx vitest run --coverage --coverage.reporter=lcov
npx c8 --reporter=lcov node --test
```

Then gate the added or modified instrumented lines against the intended target branch:

```bash
python tools/coverage_gate.py --lcov coverage/lcov.info --base origin/<dev-branch> --threshold 80
```

The gate must exit successfully before committing. If the report uses different source paths, set
`--path-prefix` to map the report paths to repository paths. A change with no measurable instrumented
lines is reported explicitly and passes; it does not claim coverage for uninstrumented changes.
