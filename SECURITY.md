# Security Policy

## Supported Versions

We actively provide security updates for the following versions of VIKI:

| Version | Supported          |
| ------- | ------------------ |
| 7.3.x   | :white_check_mark: |
| 7.2.x   | :white_check_mark: |
| < 7.2.0 | :x:                |

## Reporting a Vulnerability

As a sovereign digital intelligence, security is at the core of VIKI's architecture. If you discover a security vulnerability, we would appreciate it if you could report it to us privately.

**Please do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability:
1.  Send an email to the Orythix001 security team (or open a private security advisory on GitHub if enabled).
2.  Include a detailed description of the vulnerability.
3.  Provide steps to reproduce the issue.
4.  Include any relevant logs or screenshots.

We will acknowledge your report within 48 hours and provide a timeline for a fix.

## Security Architecture

VIKI is designed with a **Defense-in-Depth** approach:
*   **Local-First Execution**: Most operations occur on-device to minimize external attack surfaces.
*   **Action Validation**: Every skill execution is checked by `safety.validate_action(skill_name, params)` before running; prohibited patterns and admin-file access are blocked.
*   **Path Sandboxing**: File operations (filesystem_skill, dev_tools, whisper, PDF, data_analysis) are restricted to allowed roots (workspace_dir, data_dir from settings). Filesystem_skill uses these roots when available.
*   **Capability Gating**: High-risk skills (filesystem, shell) require explicit permission and are logged in `logs/viki.log`.
*   **API Authentication**: All REST endpoints are protected by `VIKI_API_KEY`.
*   **Secret Redaction**: Model output and logs redact API keys and tokens; user input and skill params are logged via `safe_for_log()`.
*   **Prompt Injection Mitigation**: Incoming prompts are sanitized against a blocklist of jailbreak-style phrases.
*   **Shell Safety**: Commands containing `;`, `&&`, `||`, or `|` require confirmation (treated as destructive). Optional LLM security scan can be enabled via `system.security_scan_requests`.
*   **Sandbox Principles**: Shell and system commands are executed within restricted environments where possible.

## Best Practices for Users

*   **Secrets Management**: Never commit your `.env` file or high-level secrets (like `VIKI_API_KEY` or `VIKI_ADMIN_SECRET`) to version control.
*   **Model Origin**: Only use trusted models from official sources (Ollama/HuggingFace) to prevent "prompt injection" or malicious weight attacks.
*   **Logs**: Periodically review `logs/viki.log` for any unauthorized capability check attempts.

---

**VIKI: Virtual Intelligence, Real Evolution.**
Designed by Orythix001. 2026.
