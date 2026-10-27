# Plan: Request form to Angular

Spec: `spec.md` (example spec written for this fixture)

## Approach

Use the React fleet inventory and dependency graph to identify the request-form leaf and its service
seams. Add Angular tests first, then implement the matching standalone form with reactive forms and the
same test IDs. Keep the shared Playwright spec as the cross-application behavior contract. Apply the
UX-v2 mockup only after parity passes, then rerun the shared spec against both apps.

## Affected files

| File | Change |
| --- | --- |
| `example-system/web-app/react-prototype/src/components/RequestForm.tsx` | source behavior and conditional validation |
| `example-system/web-app/angular-app/src/request-form.component.ts` | standalone Angular form, tests, and UX-v2 iteration |
| `example-system/web-app/angular-app/src/request-form.component.spec.ts` | Angular unit tests for form behavior and accessible errors |
| `example-system/web-app/e2e/tests/request-flow.spec.ts` | shared Playwright regression contract for both apps |
| `example-system/web-app/mockups/request-form-v2.html` | offline UX reference |
| `tools/react_fleet_scan.py` | deterministic inventory and leaf-first migration guidance |

## Data and interface changes

- Request fields: type, priority, summary, optional serial number, and optional justification.
- Shared fixture file and `data-testid` values remain unchanged; there is no API or persistent schema change.
- React props/state/hooks map to Angular inputs/signals/services/reactive forms as appropriate; design-system choices remain with the adopting team.

## Test strategy

- Existing tests expected to break and why: none; the work preserves the fixture contract.
- New tests:
  - Angular unit tests cover conditional fields, minimum justification length, and successful valid submission.
  - One Playwright spec runs against both apps and checks conditional create, validation, filtering, detail navigation, and axe violations.
  - A fixture equality test compares the React and Angular `requests.json` files byte-for-byte.
  - The scanner `--check` compares committed expected inventory, graph, backlog, and concept-map artifacts.
- Proof is the Angular unit suite and coverage plus the shared Playwright spec passing against both apps.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Similar screens drift in behavior | medium | Keep one Playwright spec and data-testid contract shared by both applications |
| UX changes hide a behavior regression | low | Apply the mockup in a separate change after parity and rerun both e2e targets |
| Lexical scanner misreads dynamic React patterns | medium | Treat its graph as a review aid and confirm findings against source and tests |

## Rollback

Revert only the UX iteration to restore the prior Angular form while retaining the behavior-parity
implementation and tests. If migration assumptions change, update this example plan before following it.
