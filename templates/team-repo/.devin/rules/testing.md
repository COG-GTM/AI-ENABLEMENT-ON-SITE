---
description: Require regression tests and a changed-line coverage gate.
trigger: always_on
---

For features, write tests before implementation. Run the relevant tests after each coherent change.
Gate commits on at least 80% changed-line coverage unless the team sets a higher threshold.
Investigate a failing test; do not weaken its assertions to get a passing result.
