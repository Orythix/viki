# Postman / Newman

## Workflow

1. Import `Security-Lab.local.postman_collection.json` into Postman.
2. Define environment variables: `baseUrl`, `apiKey`, `role`.
3. CLI (CI): `npx newman run Security-Lab.local.postman_collection.json -e local.postman_environment.json`

## When to use vs code-first API tests

- **Postman**: exploratory API testing, quick sharing with PMs, collections as living docs.
- **pytest / REST Assured**: version-controlled assertions, refactor-friendly, PR gates.

Learn both; default automation in this repo is **code-first**.
