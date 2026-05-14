# Security checklist (before running the lab)

- [ ] **Network:** Bind API/UI to `127.0.0.1` only (default in `docker-compose.yml`).
- [ ] **Secrets:** Change `LAB_API_KEY` from the dev default; never commit real keys.
- [ ] **Ollama:** Confirm `OLLAMA_URL` points to **your** local instance, not the public internet.
- [ ] **RBAC:** Review `security/policies/rbac.json`; grant `tools.shell` only to dedicated admin personas.
- [ ] **Sandbox:** Do not publish `sandbox-demo` ports; keep it on `lab_internal` only.
- [ ] **Data:** Restrict permissions on the SQLite audit volume / file (or lock down PostgreSQL role + TLS if used).
- [ ] **Updates:** Pin base images and Python deps; rebuild periodically.
- [ ] **Backups:** If audit logs leave the machine, encrypt them.
- [ ] **Legal:** Use only for systems you own or have **written authorization** to test.
