# Sandbox environments

## `demo_app` (reflected XSS)

- **Purpose:** Practice **detecting** and **fixing** XSS in a toy app inside Docker.
- **Risk:** Dangerous if exposed beyond `lab_internal`. Compose file does **not** publish its port.
- **Usage:** From the `lab-api` container, only: `http://sandbox-demo:8080/echo?q=...` via the `http_get_sandbox` tool (host allowlisted).

Do not add real credentials, customer data, or internet-facing routes to this service.
