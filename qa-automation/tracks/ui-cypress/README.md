# Cypress track (JavaScript)

## Run

```bash
cd security-lab/frontend && npm run dev
```

```bash
cd qa-automation/tracks/ui-cypress
npm install
npx cypress run --env UI_LIVE=true
```

Without `UI_LIVE=true`, the suite skips (CI-friendly).

## vs Playwright

Cypress runs **in-browser**; great DX. Playwright often wins for **multi-tab**, **parallel sharding**, and **trace** in large orgs. Learn both at a shallow level, go deep on what your target employer uses.
