# Playwright track (TypeScript)

## Run locally

Terminal 1 — frontend:

```bash
cd labs/security-lab/frontend
npm install && npm run dev
```

Terminal 2:

```bash
cd labs/qa-automation/tracks/ui-playwright
npm install
npx playwright install chromium
set QA_UI_LIVE=1
npm test
```

## Cross-browser

Add Firefox/WebKit projects in `playwright.config.ts` (`devices["Desktop Firefox"]`).

## Why Playwright over Selenium here

Faster iteration, built-in traces, auto-wait. **Selenium** remains common in enterprises — same POM patterns; swap driver for grid.
