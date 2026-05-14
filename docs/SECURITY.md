# Security Policy

General documentation index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md). API and capability setup (full tree): [viki/SECURITY_docs/SETUP.md](viki/SECURITY_docs/SETUP.md) (available in the implementation checkout).

## Supported Versions

Security fixes are applied to the most recent minor release line.

| Version | Supported          |
| ------- | ------------------ |
| 8.0.x   | :white_check_mark: |
| 7.3.x   | :white_check_mark: |
| < 7.3.0 | :x:                |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use GitHub **private vulnerability reporting**:

### Implementation repository (maintainers & invited collaborators)

1. Open the [Security tab](https://github.com/Orythix/viki/security) of the **Orythix/viki** repository
2. Click **Report a vulnerability**

### Public documentation only ([VIKI-public](https://github.com/Orythix/VIKI-public))

If you do **not** have access to the private implementation repo, report via the [Security tab on **Orythix/VIKI-public**](https://github.com/Orythix/VIKI-public/security) instead (same **Report a vulnerability** flow).

### What to include

- A clear description of the issue and its impact
- Steps to reproduce (or a minimal proof-of-concept)
- Affected version, OS, and any relevant logs (with secrets redacted)

We aim to acknowledge reports within **48 hours** and provide a remediation
timeline within **7 days** of triage. Coordinated disclosure is appreciated;
we will credit reporters in the changelog if requested.

## Security Architecture

VIKI is designed with a **defense-in-depth** approach:

* **Local-first execution** — most operations run on-device to minimize external attack surface.
* **Action validation** — every skill execution is checked by `safety.validate_action(skill_name, params)` before running. Prohibited patterns and admin-file access are blocked.
* **Path sandboxing** — file operations (`filesystem_skill`, `dev_tools`, `whisper`, `pdf`, `data_analysis`) are restricted to allowed roots (`workspace_dir`, `data_dir`).
* **Capability gating** — high-risk skills (filesystem, shell) require explicit permission and are logged in `logs/viki.log`.
* **API authentication** — all REST endpoints require `VIKI_API_KEY`.
* **Secret redaction** — model output and logs redact API keys and tokens; user input and skill params are logged via `safe_for_log()`.
* **Prompt injection mitigation** — incoming prompts are sanitized against a blocklist of jailbreak-style phrases.
* **Shell safety** — commands containing `;`, `&&`, `||`, or `|` require confirmation. Optional LLM security scan can be enabled via `system.security_scan_requests`.
* **Sandbox principles** — shell and system commands are executed within restricted environments where possible.

## Best Practices for Operators

* **Secrets management** — never commit `.env` or operational secrets (`VIKI_API_KEY`, `VIKI_ADMIN_SECRET`) to version control. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
* **Default keys are dead** — any `VIKI_API_KEY` value found in old documentation or example files (e.g. the historical `REDACTED-OLD-KEY-ROTATE-VIKI_API_KEY` placeholder) is invalid. Always generate your own.
* **Model origin** — only use trusted models from official sources (Ollama / Hugging Face) to mitigate prompt-injection or malicious-weight attacks.
* **Log review** — periodically review `logs/viki.log` for unauthorized capability-check attempts.

---

For setup details, see [`viki/SECURITY_docs/SETUP.md`](viki/SECURITY_docs/SETUP.md).

---

*Runbook version: aligned with VIKI v8.0.0 (Industrial). Update this file when default ports, flags, or critical architecture patterns change.*
