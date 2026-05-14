# QA automation — multi-stack learning monorepo

**Parent repository:** [VIKI](../README.md) (this folder lives next to `viki/`, `ui/`, and `labs/security-lab/`).

Hands-on tracks for **API, UI, performance, SQL, mobile patterns**, plus **CI samples** (GitHub Actions, Azure DevOps, Jenkins). Primary API target: **`labs/security-lab`** (local, defensive).

## Tracks at a glance

| Path | Stack |
|------|--------|
| **`qa_lab/`** + **`tests/`** | **Python**, **pytest**, **httpx** |
| **`tracks/java-api/`** | **Java 17**, **JUnit 5**, **REST Assured** |
| **`tracks/ui-playwright/`** | **TypeScript**, **Playwright** |
| **`tracks/ui-cypress/`** | **JavaScript**, **Cypress** |
| **`tracks/performance/`** | **k6** (+ JMeter doc) |
| **`tracks/postman/`** | **Postman** collection + **Newman** notes |
| **`tracks/sql/`** | **SQL** audit / DB testing patterns |
| **`tracks/mobile-appium/`** | **Appium 2** README + homework |
| **`docker/`** | Compose / sidecar patterns |
| **`ci/`** | **Azure** + **Jenkins** examples |
| **`docs/SYLLABUS.md`** | Week-by-week curriculum (all stacks) |
| **`docs/STACK_INDEX.md`** | Where to learn each tool |

## Quick commands

**Python (CI-safe unit tests):**

```powershell
cd labs/qa-automation
pip install -r requirements.txt
pytest tests\unit -q
```

**Python live** (API must be running — see `labs/security-lab` README):

```powershell
$env:QA_LIVE_API="1"
pytest tests\live -m smoke -v
```

**Java:**

```powershell
cd labs/qa-automation\tracks\java-api
mvn -q test
```

**k6** (install k6 first): `k6 run tracks/performance/k6-ci-smoke.js`

**Playwright:** see `tracks/ui-playwright/README.md` (`QA_UI_LIVE=1` + Vite).

## Continuous integration

- **GitHub:** `.github/workflows/labs/qa-automation.yml` runs Python unit, Java, k6; Playwright runs with skips unless you enable UI.
- **Azure / Jenkins:** copy files under `ci/`.

## Defaults (adjusted for “everything”)

You can specialize later; this repo exposes **all** of the following in some form:

**Languages:** Python, Java, TypeScript, JavaScript  
**UI:** Playwright, Cypress (+ Selenium doc via STACK_INDEX)  
**API:** httpx, REST Assured, Postman  
**Runners:** pytest, JUnit 5 (TestNG: extend in Java track)  
**Perf:** k6, JMeter guidance  
**CI:** GitHub Actions, Azure DevOps example, Jenkins example  
**Data:** SQL examples  
**Mobile:** Appium pattern doc  
**Containers:** Docker notes  

## Security

- Never commit real **API keys**; use CI secrets.
- Run **load tests** only against environments you own or are authorized to stress.

## Curriculum

Open **`docs/SYLLABUS.md`** for the full roadmap and rubrics.

**Repo-wide doc index:** [docs/DOCUMENTATION.md](../docs/DOCUMENTATION.md).
