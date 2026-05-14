# Java API track — REST Assured + JUnit 5

## Why this stack

- **REST Assured**: fluent API assertions common in Java microservice shops.
- **JUnit 5**: industry default; use **TestNG** if your employer standardizes it (same patterns, different annotations).

## Run (unit-style, always passes in CI)

```bash
cd labs/qa-automation/tracks/java-api
mvn -q test
```

`SecurityLabApiLiveIT` is **disabled** unless `QA_LIVE_JAVA=1`.

## Live run

```bash
export QA_LIVE_JAVA=1
export QA_BASE_URL=http://127.0.0.1:8000
export QA_API_KEY=dev-lab-change-me
mvn test
```

## Homework

- Add a test for `POST /api/v1/security/classify` with JSON body (auth headers).
- Add **Awaitility** + polling for async endpoints (optional).
- **TestNG:** duplicate one class with `@Test`, `testng.xml`, and Maven Surefire/TestNG — common in older Java shops.
