# Syllabus — full QA automation track (multi-stack)

**Capstone:** One repo showing **Python + Java API**, **k6**, **Playwright** (or Cypress), **SQL**, **CI** — plus a **3–5 min video** of a failing test → root cause → green run.

**Time:** ~8–10 hrs/week to do every week; ~4–5 hrs/week if you merge pairs. See **`STACK_INDEX.md`** to pick tools by job market.

---

## Phase map (16 themes × multiple tools)

| Week | Theme | Primary hands-on | Also touch |
|------|--------|------------------|------------|
| 1 | Fundamentals, SDLC/STLC, test strategy | Write strategy for `security-lab` | Risk-based scope |
| 2 | Test design, traceability | Traceability table REQ → test | Markdown / Confluence style |
| 3 | API testing — Python | `tests/live`, `qa_lab/client.py` | Status codes, auth headers |
| 4 | API — Java | `tracks/java-api` REST Assured | Compare with pytest style |
| 5 | API — Postman / Newman | `tracks/postman` collection | When collections beat code |
| 6 | Framework architecture | Client layer, config, no duplication | Logging without secrets |
| 7 | Data-driven & negative tests | `pytest.mark.parametrize` | Java `@ParameterizedTest` (homework) |
| 8 | DB / SQL testing | `tracks/sql`, audit queries | Reconciliation pattern |
| 9 | UI — Playwright | `tracks/ui-playwright` | POM, role selectors |
| 10 | UI — Cypress or Selenium | `tracks/ui-cypress` or Selenium homework | Cross-browser matrix |
| 11 | Performance — k6 | `k6-ci-smoke.js`, `security-lab-smoke.js` | Thresholds, stages |
| 12 | Performance — JMeter | `tracks/jmeter` exercise | .jmx + CLI report |
| 13 | CI/CD — GitHub Actions | `qa-automation.yml` | Path filters, artifacts |
| 14 | CI — Azure + Jenkins | `ci/azure-pipelines.example.yml`, `Jenkinsfile.example` | Multi-stage gates |
| 15 | Mobile — Appium | `tracks/mobile-appium` | Capabilities, device farm |
| 16 | AI-assisted QA + portfolio | Prompts for test ideas & RCA | STAR stories, architecture diagram |

---

## Week 1 — Testing fundamentals & strategy

**Goals:** Verification vs validation; **test strategy** one-pager for `security-lab`.

**Reading:** Test pyramid; shift-left / shift-right.

**Homework:** Traceability: 5 requirements → manual or automated (tool-agnostic).

**Rubric:** Out-of-scope explicit; risks prioritized.

---

## Week 2 — Manual + bug reporting

**Goals:** Exploratory charter; **defect report** devs respect (repro, expected/actual, build, logs).

**Homework:** 2 exploratory sessions on security-lab UI; file 1 **fake** bug in a personal template.

**Rubric:** Minimal repro; no blameful language.

---

## Week 3 — API (Python)

**Goals:** pytest, httpx, markers, live vs unit split.

**Hands-on:** `tests/unit`, `tests/live`, env `QA_LIVE_API`.

**Homework:** `GET /api/v1/monitoring/summary` assertions.

**Rubric:** 401 without key; passes with key.

---

## Week 4 — API (Java)

**Goals:** REST Assured fluency; JUnit 5 conditional live tests.

**Hands-on:** `tracks/java-api` — `mvn test`; enable `QA_LIVE_JAVA=1` locally.

**Homework:** Classify endpoint with JSON body + auth headers.

**Rubric:** No hard-coded secrets in source.

---

## Week 5 — Postman / Newman

**Goals:** Collections as docs; CLI in pipeline.

**Hands-on:** Import `tracks/postman/Security-Lab.local.postman_collection.json`.

**Homework:** Add “Classify” request; export updated JSON.

**Rubric:** Variables for `baseUrl` / `apiKey`.

---

## Week 6 — Framework architecture

**Goals:** Why **client** + **config** layers scale.

**Hands-on:** Extend Python `SecurityLabClient` with one new method; mirror idea in Java if desired.

**Homework:** README section “how to add an endpoint.”

**Rubric:** Zero duplicate base URLs in tests.

---

## Week 7 — Data-driven & authZ

**Goals:** Parametrization; role matrix (`lab_admin` vs `observer`).

**Hands-on:** Python `parametrize` safe strings for `/security/classify`.

**Homework:** Java `@ParameterizedTest` or TestNG `DataProvider` equivalent.

**Rubric:** Failure output shows which row failed.

---

## Week 8 — SQL & data integrity

**Goals:** Audit queries; API → DB cross-check pattern.

**Hands-on:** `tracks/sql/audit_queries.sql` against a **copy** of lab DB.

**Homework:** Document one reconciliation query (counts / sums).

**Rubric:** Read-only on shared DBs; disposable DB for destructive tests.

---

## Week 9 — Playwright (TypeScript)

**Goals:** Stable locators, traces, HTML report.

**Hands-on:** `tracks/ui-playwright` with `QA_UI_LIVE=1`.

**Homework:** Second spec: “Run harness” button flow (may need API up).

**Rubric:** Prefer `getByRole` / `data-testid` over long CSS.

---

## Week 10 — Cypress or Selenium

**Goals:** Second UI stack for résumé breadth.

**Hands-on:** `tracks/ui-cypress` with `UI_LIVE=true`.

**Homework (Selenium):** One login/dashboard flow in Java or Python — reuse POM naming.

**Rubric:** No `Thread.sleep` as primary sync.

---

## Week 11 — Performance (k6)

**Goals:** Thresholds, stages, CI-friendly script.

**Hands-on:** `k6-ci-smoke.js` in CI; `security-lab-smoke.js` locally.

**Homework:** Add `stages` ramp; document error budget.

**Rubric:** Never load-test unauthorized targets.

---

## Week 12 — Performance (JMeter)

**Goals:** `.jmx`, CLI, HTML report.

**Hands-on:** `tracks/jmeter/README.md` exercise.

**Homework:** Check in **small** `.jmx` **or** gitignore + doc only (team policy).

**Rubric:** Parameterized host.

---

## Week 13 — CI: GitHub Actions

**Goals:** Path filters, matrices, artifacts, flaky policy.

**Hands-on:** Open PR touching `qa-automation/`; inspect workflow.

**Homework:** Add scheduled **weekly** workflow comment or draft YAML.

**Rubric:** Secrets via `GITHUB_SECRET`, not literals.

---

## Week 14 — CI: Azure DevOps & Jenkins

**Goals:** Enterprise orchestration patterns.

**Hands-on:** Adapt `ci/azure-pipelines.example.yml` / `Jenkinsfile.example` to a dummy project.

**Homework:** Publish test results task / `junit` step.

**Rubric:** Failed stage blocks deploy (where appropriate).

---

## Week 15 — Mobile (Appium)

**Goals:** Capabilities, emulator, one smoke flow.

**Hands-on:** `tracks/mobile-appium/README.md`.

**Homework:** Start emulator; run one test locally (no cloud keys in repo).

**Rubric:** No personal devices without consent.

---

## Week 16 — AI-assisted QA + interview prep

**Goals:** Safe prompts for test ideas & RCA; portfolio narrative.

**Deliverables:** Architecture diagram; 3 **STAR** stories; mock interview (pyramid, flake, prioritization).

**Homework:** 3 prompts (negative auth, rate limit, flaky triage) — **no secrets in prompts**.

**Rubric:** You explain **maintainability vs coverage** tradeoffs clearly.

---

## Interview question bank (cross-stack)

- How do you cut flake in UI automation?
- Where does contract testing fit vs E2E?
- How do you prioritize when release is tomorrow?
- How would you gate a microservice deploy with **smoke + contract + metrics**?

---

## Common mistakes (all tools)

- Sleeping instead of **explicit waits** / retries on the right layer.  
- **Shared mutable** test data in parallel.  
- **Secrets** in repos or reports.  
- **E2E-only** CI for large apps.  
- No **ownership** for failing jobs.

---

## Scaling strategies

- Parallel shards (`pytest-xdist`, Playwright workers, k6 VUs).  
- **Quarantine** flaky tests with deadlines.  
- **Service virtualization** for unstable deps.  
- **Quality metrics:** flake rate, MTTR for red pipeline, critical-path coverage.
