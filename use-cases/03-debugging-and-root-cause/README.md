# Debugging and Root Cause

## Outcome

Reproduce a seeded defect, trace the failing path, identify the root cause, add a regression test, and verify a minimal fix.

## Candidate demo

- Run a known failing test.
- Form and test hypotheses from source and sanitized output.
- Distinguish root cause from symptoms.
- Add a regression test before the fix.
- Verify the focused change.

## Evidence

The defect is reproducible, the test fails before and passes after, and the explanation matches the code path.

## Guardrails

Use fabricated logs and a synthetic defect. Do not connect to a live system or expose stack traces containing sensitive values.
