# Spec: Request form to Angular

Status: example spec written for this fixture
Requirement IDs touched: fixture behavior contract only
Tracker: none. Hazards: none.

## Problem

The synthetic equipment service-request prototype is implemented in React. The team needs a bounded
example of migrating its request form to Angular without changing the user-visible behavior or the
shared request contract.

## Users

- A web developer needs to see how React component, state, hook, and form concepts map to Angular.
- A reviewer needs a repeatable test contract for the React prototype and Angular implementation.

## User stories and acceptance criteria

### US-1: Create a conditional service request

Given a user selects repair and urgent priority
When the user submits without a serial number or a 20-character justification
Then the form shows the applicable validation messages and creates no request.

### US-2: Preserve the request workflow

Given the user enters valid request details
When the form is submitted
Then the request appears in the shared list and can be opened by its route parameter.

### US-3: Iterate on form usability

Given the Angular request form preserves the shared behavior contract
When the v2 form layout is applied
Then labels, an error summary, responsive layout, focus states, and ARIA descriptions are present
without changing the shared Playwright behavior assertions.

## Non-goals

- Translating React source mechanically or choosing a design system for a real application.
- Connecting to external services, using customer data, or claiming product availability in any authorization boundary.
- Replacing the React prototype or proving equivalence outside the fixture's tested flows.

## Constraints

- Both apps use the same synthetic `requests.json` and `data-testid` contract.
- Tests and scanner outputs are deterministic and runnable offline after dependencies and browser binaries are cached.
- The shared Playwright contract covers conditional create, validation, filtering, route detail, and accessibility.
- No external writes or network calls are part of the fixture behavior.

## Open questions

- None for this fixture example; product-specific design decisions must be confirmed by the adopting team.
