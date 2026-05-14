import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.QA_UI_URL || "http://127.0.0.1:5173";

/**
 * Playwright: prefer role + testid selectors (see labs/security-lab frontend buttons).
 * CI: set QA_UI_URL; start Vite dev server or serve static build before test.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
