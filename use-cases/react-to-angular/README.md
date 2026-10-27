# React prototype to Angular application

## Why and when

Use this lane when a team wants a bounded, reviewable migration from a React prototype to Angular.
It inventories the React tree, documents concept mappings, migrates leaf-first, and keeps one shared
Playwright spec as the behavior contract.

## What you need

- This repository and its synthetic `example-system/web-app/` fixture.
- Node.js/npm packages and Playwright browser binaries installed or cached before working offline.
- A real application's owner to decide its Angular design system and migration boundaries.

## First 15 minutes

| Desktop | CLI |
| --- | --- |
| 1. Follow [Get the files](../../README.md#get-the-files-once) and open the repository folder. 2. Type `/` in chat and confirm `/react-to-angular`, `/ui-iterate`, `/spec-driven`, `/tdd`, `/plan-to-tracker`, `/test-backfill`, and `/sonar-gate` are listed (confirm on your build). 3. In Ask mode, send `/react-to-angular Scan example-system/web-app/react-prototype and explain the leaf-first plan.` 4. Switch to Plan mode and send `/spec-driven Migrate the request form using the shared fixture contract`; the plan lands under `~/.devin/plans/`. 5. Use Code/Agent mode to work through the tasks one at a time. | From the clone's parent, run `cd AI-ENABLEMENT-ON-SITE`, then `devin rules list` and `devin skills list`. Start the interactive CLI with `devin`, or send the Ask prompt with `devin -p -- "/react-to-angular Scan example-system/web-app/react-prototype and explain the leaf-first plan."`. |

## Install once (offline)

See the [web fixture setup guide](../../example-system/web-app/README.md) for the Node.js 24.15+
requirement and the approved-mirror cache workflow. Resolve the pinned packages before disconnecting,
then run each command from the repository root:

```sh
# Run each line separately, starting from the repository root.
cd example-system/web-app/react-prototype && npm ci
cd example-system/web-app/angular-app && npm ci
cd example-system/web-app/e2e && npm ci
```

## Steps

| Step | Desktop | CLI |
| --- | --- | --- |
| Ask and plan | `/react-to-angular` in Ask mode; review the graph and concept map, then `/spec-driven` in Plan mode | `python tools/react_fleet_scan.py <react-tree> --name <name>`; draft `spec.md`, `plan.md`, `tasks.md` |
| Track | `/plan-to-tracker specs/002-request-form-to-angular/tasks.md --project <KEY>`; inspect the dry run | `python tools/plan_to_tracker.py specs/002-request-form-to-angular/tasks.md --project <KEY>` |
| Migrate leaf-first | On a feature branch, `/tdd` per Angular unit; run unit tests, coverage, and shared e2e | `cd example-system/web-app/angular-app && npm test && npm run test:coverage`<br>`cd ../e2e && npm run e2e:react && npm run e2e:angular`<br>`cd ../../../ && python tools/coverage_gate.py --lcov example-system/web-app/angular-app/coverage/equipment-request/lcov.info --base origin/<dev-branch> --threshold 80 --path-prefix example-system/web-app/angular-app` |
| Iterate the UI | `/ui-iterate`; preview the local app, inspect errors, run axe, capture before/after | Edit mockup/component, run the local server and shared Playwright spec, save screenshots |
| Review | Run `/sonar-gate` when approved; developer reviews Devin-drafted commit message | `python tools/check_repo.py`; `python tools/golden_path.py`; review test/evidence files |

## What the fixture shows

The parity baseline records **2 React unit tests** with React line coverage of **89.04%**, and
**10 Angular unit tests** with Angular line coverage of **99.18%**. After the UX iteration and the
validation/focus fixes, Angular has **14 unit tests** and **99.37%** line coverage. The shared
Playwright spec passed **2/2 tests against each app** before the UX iteration and **3/3 against each
app** after; both post-iteration axe runs recorded zero violations. The React and Angular fixture data
files are checked for equality.
See `example-system/web-app/evidence/parity.json` and `ux-upgrade.json` for the run records, and the
scanner's committed `expected/` files for its deterministic inventory.

## What it does not prove

The scanner is lexical, not a TypeScript compiler or architecture oracle. The synthetic fixture does
not establish parity outside its tested flows, select a design system, or prove an adopting team's
product and offline-preview availability. Confirm those decisions and Devin features on your build.
