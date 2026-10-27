# React prototype to Angular application

## Why and when

Use this lane when a team wants a bounded, reviewable migration from a React prototype to Angular.
It inventories the React tree, documents concept mappings, migrates leaf-first, and keeps one shared
Playwright spec as the behavior contract.

## What you need

- This repository and its synthetic `example-system/web-app/` fixture.
- Node.js/npm packages and Playwright browser binaries installed or cached before working offline.
- A real application's owner to decide its Angular design system and migration boundaries.

## Steps

| Step | Desktop | CLI |
| --- | --- | --- |
| Ask and plan | `/react-to-angular` in Ask mode; review the graph and concept map, then `/spec-driven` in Plan mode | `python tools/react_fleet_scan.py <react-tree> --name <name>`; draft `spec.md`, `plan.md`, `tasks.md` |
| Track | `/plan-to-tracker specs/<nnn>-<slug>/tasks.md --project <KEY>`; inspect the dry run | `python tools/plan_to_tracker.py specs/<nnn>-<slug>/tasks.md --project <KEY>` |
| Migrate leaf-first | On a feature branch, `/tdd` per Angular unit; run unit tests, coverage, and shared e2e | `npm test -- --run`; run coverage; then `npm run e2e:react` and `npm run e2e:angular` |
| Iterate the UI | `/ui-iterate`; preview the local app, inspect errors, run axe, capture before/after | Edit mockup/component, run the local server and shared Playwright spec, save screenshots |
| Review | Run `/sonar-gate` when approved; developer reviews Devin-drafted commit message | `python tools/check_repo.py`; `python tools/golden_path.py`; review test/evidence files |

## What the fixture shows

The committed evidence records **2 React unit tests**, **10 Angular unit tests**, React line coverage
of **89.04%**, Angular line coverage of **99.18%** before the UX iteration and **99.31%** after it.
The shared Playwright spec passed **2/2 tests against each app** before and after the UX change; the
axe runs recorded zero violations. The React and Angular fixture data files are checked for equality.
See `example-system/web-app/evidence/parity.json` and `ux-upgrade.json` for the run records, and the
scanner's committed `expected/` files for its deterministic inventory.

## What it does not prove

The scanner is lexical, not a TypeScript compiler or architecture oracle. The synthetic fixture does
not establish parity outside its tested flows, select a design system, or prove an adopting team's
product and offline-preview availability. Confirm those decisions and Devin features on your build.
