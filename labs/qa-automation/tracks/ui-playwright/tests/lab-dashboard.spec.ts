import { test, expect } from "@playwright/test";

const uiLive = !!process.env.QA_UI_LIVE;

test.describe("Security lab dashboard", () => {
  test.skip(!uiLive, "Set QA_UI_LIVE=1 and start labs/security-lab/frontend (npm run dev)");

  test("shows learning lab heading", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /AI Security Learning Lab/i })).toBeVisible();
  });

  test("refresh button exists", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: /Refresh monitoring/i })).toBeVisible();
  });
});
