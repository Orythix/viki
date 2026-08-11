# 🔐 Zero-Leakage Privacy Sanitizer Rule

This rule enforces strict local anonymization before outbound prompt transmission.

## Rules & Constraints
1. **Local Anonymization**:
   - Outbound prompt payloads routed to cloud endpoints or remote server IPs must be processed through `PrivacySanitizer.sanitize()`.
2. **Redacted Patterns**:
   - API Keys: `sk-...`, `ghp_...`, `xoxb-...`, `AKIA...`.
   - Secret Credentials: `api_key`, `secret_key`, `password`, `access_token`.
   - PII & Identifiers: Emails and private IP addresses (`10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`).
3. **Local Re-hydration**:
   - Redacted placeholders (e.g. `[REDACTED_API_KEY_1]`) must be re-hydrated back to their original values locally upon response arrival via `PrivacySanitizer.rehydrate()`.
