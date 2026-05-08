# Selenium WebDriver 4 (pattern)

## When employers say “Selenium”

They often mean **WebDriver** with **Java**, **C#**, **Python**, or **JS** bindings, sometimes via **Grid** or cloud providers (BrowserStack, Sauce).

## Minimal exercise (homework)

1. Add `selenium` (Python) or Selenium Java dependency.
2. Open `http://127.0.0.1:5173` (security-lab frontend).
3. Find the **h1** with `By.cssSelector("h1")` or `By.tagName("h1")`.
4. Prefer migrating to **`data-testid`** locators in the app for stability.

## Relation to Playwright / Cypress

Same **Page Object** discipline; different **wait** and **driver** model. Learn **one** web tool deeply (this repo: Playwright), then map concepts to Selenium in **1–2 days** when a job requires it.
