# Example attack concepts and defenses (educational)

> **Only use on systems you own or are authorized to test.** This document describes **categories** of behavior, not step-by-step offensive recipes.

## Prompt injection (instruction override)

- **Idea:** Untrusted text tries to change model behavior or exfiltrate secrets.
- **Lab defense:** `security/injection_detector.py` heuristic + system policy in `AgentCore`; **observe_only** flag on `/api/v1/chat` for training runs that must not block.
- **Real-world defense:** Tool allowlists, separate system channel, structured tool JSON (not free-form), output egress filtering, monitoring.

## Tool abuse (shell / SSRF)

- **Idea:** Coerce the agent to run arbitrary commands or fetch internal URLs.
- **Lab defense:** RBAC (`tools.shell`), subprocess **without** `shell=True`, binary allowlist, HTTP host allowlist for `http_get_sandbox`.
- **Real-world defense:** Run tools in dedicated microVMs / gVisor / separate K8s namespaces; network policies; secretless workload identity.

## Memory poisoning

- **Idea:** Store untrusted “facts” that later appear near system instructions.
- **Lab defense:** Sanitize on ingest (`sanitizer.py`); cap deque size; do not promote user text to system prompts automatically.
- **Real-world defense:** Signed memory sources, provenance metadata, retrieval filters.

## XSS in sandbox app

- **Idea:** Reflected HTML in `sandbox/demo_app` for **local** practice.
- **Lab defense:** Container not exposed to LAN; learners patch `echo()` to use encoding + CSP.
- **Never** use this pattern in production.

## Model secret echo

- **Idea:** Model repeats API-like strings from context.
- **Lab defense:** `output_filter.py` regex redaction (best-effort).
- **Real-world defense:** Never place live secrets in prompts; use vault + short-lived tokens; DLP on outputs.

## Observability (defensive)

- **Idea:** Operators need to spot repeated blocks, tool failures, and resource spikes without exposing raw prompts broadly.
- **Lab defense:** `GET /api/v1/monitoring/summary` (metrics + optional `psutil` snapshot + alerts derived from audit); `POST /api/v1/security/analyze` for offline triage of a single string (no LLM call).
- **Real-world defense:** Central logging with retention policies, SIEM correlation, and strict access to security dashboards.
