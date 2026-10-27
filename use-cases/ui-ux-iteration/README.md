# Local UI/UX iteration

## Why and when

Use this lane to refine a local interface from a self-contained mockup while keeping the functional
contract intact. It uses the Angular request form in the paired web fixture.

## What you need

- `example-system/web-app/mockups/request-form-v2.html` and the React/Angular fixture.
- Node.js/npm packages and Playwright browser binaries available locally.
- Devin Desktop preview if available; preview and screenshot capture in an offline or FedRAMP
  environment are **confirm on your build**.

## Steps

| Step | Desktop | CLI |
| --- | --- | --- |
| Inspect | `/ui-iterate` the local mockup or component; preview the local server and send captured errors | Start the local app and open the mockup from disk |
| Change | Apply the form layout, labels, error summary, ARIA descriptions, and focus states | Edit the static HTML or Angular component/CSS |
| Prove | Run axe and the shared behavior spec; capture before/after screenshots | Run `npm run e2e:react` and `npm run e2e:angular`; use Playwright screenshots |
| Share | Share a downloaded HTML file or screenshot through an approved channel, not a live URL | Save HTML/screenshots in the evidence folder; stop the servers |

## What the fixture shows

The pre- and post-iteration records in `example-system/web-app/evidence/ux-upgrade.json` show the
Angular line coverage at **99.37%**, **14/14 Angular unit tests**, and **3/3 shared Playwright tests
on each app** after the change. Both axe runs recorded zero violations. The mockup and screenshot
evidence are local files.

## What it does not prove

A screenshot proves only the captured appearance. The shared test assertions demonstrate only the
fixture's specified request flow. They do not establish customer-specific usability, compatibility,
or whether Desktop preview is available in an offline or FedRAMP environment; confirm that on your
build.
