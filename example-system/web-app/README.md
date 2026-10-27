# Equipment service request web fixture

The paired apps are customer-neutral synthetic fixtures. `react-prototype/public/requests.json` and
`angular-app/public/requests.json` are identical local seed data; each app loads it from its own localhost
server and makes no external API requests.

## Requirements and offline setup

- Node.js 24.15+ and npm (Angular 22.0.x requires Node `^22.22.3 || ^24.15.0 || ^26.0.0`).
- Use a team-approved internal npm mirror. `.npmrc.example` is an inactive template; copy it to `.npmrc`
  only after replacing the placeholder with the approved mirror. Resolve and cache the pinned packages
  on an approved connected machine, then transfer the lockfiles and package cache through the team's
  approved offline process.
- Playwright can use a provisioned internal browser cache with `PLAYWRIGHT_BROWSERS_PATH`. To use local
  Chrome instead, set `BROWSER_CHANNEL=chrome`; the config passes `channel: "chrome"`.

## Run each app

```sh
cd example-system/web-app/react-prototype
npm ci
npm run dev
```

```sh
cd example-system/web-app/angular-app
npm ci
npm start
```

Both apps expose the same request form, list filter/sort, detail route, and `data-testid` contract.
The Angular app uses standalone components, signals, reactive forms, Router, `HttpClient`, and an
injectable settings service. Its default Angular CLI unit runner is Vitest.

## Unit tests and coverage

```sh
cd example-system/web-app/react-prototype
npm test
npm run test:coverage
```

```sh
cd example-system/web-app/angular-app
npm test
npm run test:coverage
```

Angular line coverage is gated at 85% and emits `coverage/lcov.info`.

## Shared regression test

```sh
cd example-system/web-app/e2e
npm ci
npm run e2e:react
npm run e2e:angular
```

The same Playwright spec runs against either local server through `BASE_URL`; the config starts the
selected app. It covers conditional creation, field validation, filtering, the detail route, and a
critical-only axe scan. Test videos are saved by Playwright in its test-results directory.

## UX iteration

Open `mockups/request-form-v2.html` from disk. It is self-contained and has no remote fonts, assets, or
scripts. Copy the interaction changes into the Angular request form only after both apps pass the shared
regression spec; keep the behavior contract unchanged.
