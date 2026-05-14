# Threat model (local learning lab)

## Scope

- **In scope:** Abuse of the lab API (prompt injection, tool abuse, SSRF attempts against non-allowlisted hosts), leakage of local secrets via model output, RBAC bypass via forged headers, DoS via large payloads or high request rates.
- **Out of scope:** Attacks against third-party systems, malware delivery, credential harvesting from real users (this lab must not collect real credentials).

## Trust boundaries

| Boundary | Trusted | Untrusted |
|----------|---------|-----------|
| Browser / CLI operator | Assumed trusted if API key is secret | N/A |
| HTTP request body | — | All JSON fields |
| Ollama | Trusted local service | Model output treated as untrusted (filtered) |
| `sandbox-demo` | Isolated container; intentionally weak | Reflected input (XSS) |
| SQLite audit file | Host filesystem | Tampering if host compromised |
| PostgreSQL audit | DB server | Credential theft, SQL injection if app misconfigured |
| `/api/v1/monitoring/summary` | Authenticated operators | Aggregates sensitive operational metadata; keep API key rotation + localhost bind |

## STRIDE highlights

- **Spoofing:** API key + role headers (`X-Lab-API-Key`, `X-Lab-Role`) — weak for multi-tenant; replace with OAuth2/JWT for shared labs.
- **Tampering:** Audit DB file permissions; volume mounts in Docker.
- **Repudiation:** Mitigated by audit log (local); add signed logs for compliance scenarios.
- **Information disclosure:** Output filtering + log redaction; never log raw prompts with secrets.
- **Denial of service:** Rate limiting; Ollama timeouts; prompt size caps.
- **Elevation:** RBAC on tools; shell allowlist; HTTP host allowlist.

## Residual risk

Heuristic injection detection is **not** a complete defense. Assume motivated bypass. Combine with policy constraints, human review for risky tools, and hardware isolation for untrusted model weights.
