# Performance track — k6 (primary) + JMeter notes

## k6 — CI-safe demo

```bash
k6 run labs/qa-automation/tracks/performance/k6-ci-smoke.js
```

Install: https://k6.io/docs/get-started/installation/

## k6 — labs/security-lab (local)

Start the API, then:

```bash
set QA_BASE_URL=http://127.0.0.1:8000
set QA_API_KEY=your-key
k6 run labs/qa-automation/tracks/performance/labs/security-lab-smoke.js
```

## JMeter

Many enterprises still use **.jmx** in CI. Pattern: parameterize host/port, fail build on SLA breach, archive **.jtl** + HTML report.

Homework: record a simple Thread Group against `/health`, parameterize `BASE_URL`, check response code.

See `../jmeter/README.md`.

## Load vs stress

- **Load**: expected traffic shape, assert p95 latency + error rate.
- **Stress**: push past capacity, observe degradation (k6 `stages` with ramp).
