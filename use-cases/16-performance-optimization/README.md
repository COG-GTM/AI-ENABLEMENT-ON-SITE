# Performance Optimization

## Outcome

Use a reproducible synthetic benchmark to locate a bottleneck, make a focused change, and measure the result without harming correctness.

## Candidate demo

- Establish a deterministic baseline.
- Profile or instrument a local synthetic workload.
- Form and test one optimization hypothesis.
- Preserve behavior with tests.
- Compare before-and-after measurements.

## Evidence

Measurements use the same environment and workload, correctness checks pass, and trade-offs are documented.

## Guardrails

Do not load-test a shared or live service, collect real telemetry, disable safeguards, or claim gains from noncomparable measurements.
