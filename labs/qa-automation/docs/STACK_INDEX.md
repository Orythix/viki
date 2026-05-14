# Tooling index — what lives where

Parent repo documentation map: [docs/DOCUMENTATION.md](../../docs/DOCUMENTATION.md).

| You want to learn… | Start here | CI in this repo |
|---------------------|------------|-----------------|
| **Python + pytest + httpx** | `qa_lab/`, `tests/` | ✅ `labs/qa-automation.yml` (unit) |
| **Java + REST Assured + JUnit 5** | `tracks/java-api/` | ✅ same workflow |
| **TestNG** | Same patterns as JUnit; swap annotations (`@Test`, `suite.xml`) | Add Maven Surefire profile (homework) |
| **TypeScript + Playwright** | `tracks/ui-playwright/` | ✅ optional job (skips UI without `QA_UI_LIVE`) |
| **Cypress** | `tracks/ui-cypress/` | Manual / your pipeline |
| **Selenium 4** | `tracks/selenium/README.md` | Homework: WebDriver + Grid |
| **Postman** | `tracks/postman/` | `newman` in your pipeline |
| **k6** | `tracks/performance/` | ✅ public smoke script |
| **JMeter** | `tracks/jmeter/README.md` | Bring your own `.jmx` |
| **SQL** | `tracks/sql/` | Pair with disposable DB in tests |
| **Appium** | `tracks/mobile-appium/` | Device lab / local emulator |
| **Docker** | `docker/README.md` | Compose SUT, run tests from host |
| **GitHub Actions** | `.github/workflows/labs/qa-automation.yml` | — |
| **Azure DevOps** | `ci/azure-pipelines.example.yml` | Copy to your org |
| **Jenkins** | `ci/Jenkinsfile.example` | Paste into Jenkins |

## Suggested learning order (full-stack QA)

1. Python API unit + live (`tests/`)
2. Java API config + REST Assured (`tracks/java-api/`)
3. k6 thresholds (`tracks/performance/`)
4. Playwright POM (`tracks/ui-playwright/`)
5. SQL audit checks (`tracks/sql/`)
6. Postman for exploration (`tracks/postman/`)
7. Cypress or Selenium if job descriptions require it
8. Appium when you touch mobile releases
