# JMeter (enterprise pattern)

## Why JMeter still appears in job postings

GUI-friendly for non-dev testers; huge plugin ecosystem; common in **on-prem** QA.

## Suggested exercise (no binary committed)

1. JMeter GUI → Thread Group (5 threads, 30s) → HTTP Request to `${BASE_URL}/health`.
2. Add **Response Assertion** (code 200).
3. Save as `lab-health.jmx` locally (gitignore if large).
4. CLI: `jmeter -n -t lab-health.jmx -l results.jtl -e -o report/`

## vs k6

- **k6**: JavaScript, Git-friendly, developer-centric.
- **JMeter**: XML plans, GUI, heavy JVM — still valid where mandated.

This repo standardizes examples on **k6**; use JMeter where your employer requires it.
