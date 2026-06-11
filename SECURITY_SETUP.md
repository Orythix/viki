# VIKI Security Setup Guide

**Last updated:** 2026-06-12 (v8.3.0 The Code Eternal)

## Critical: Set Up Before Running

The following environment variables are now **required** for secure operation:

### 1. API Key (Required for API Server)

```bash
# Generate a secure API key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set the environment variable
export VIKI_API_KEY="your-generated-key-here"

# Windows PowerShell
$env:VIKI_API_KEY="your-generated-key-here"
```

**Messaging Gateways:** The Discord, Telegram, Slack, and WhatsApp bridges use this key to authenticate with the core nexus when running in distributed mode.

### 2. Admin Secret (Required for Admin Commands)

```bash
# Generate a secure admin secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Set the environment variable
export VIKI_ADMIN_SECRET="your-generated-secret-here"

# Windows PowerShell
$env:VIKI_ADMIN_SECRET="your-generated-secret-here"
```

**Usage:**
```
ADMIN ADMIN_ALPHA_001 your-generated-secret-here SHUTDOWN
```

### 3. Gmail / Google Calendar (Optional integrations)

When `integrations.gmail.enabled` or `integrations.google_calendar.enabled` are set in settings:

- **Gmail**: Set `VIKI_GMAIL_CREDENTIALS_PATH` to the path of your Google OAuth2 client JSON (from Google Cloud Console). Token is stored in `data_dir/gmail_token.json`. Do not commit credentials or token.
- **Google Calendar**: Set `VIKI_GOOGLE_CALENDAR_CREDENTIALS_PATH` (or use the same JSON as Gmail). Token in `data_dir/google_calendar_token.json`.

Keep credentials and token files out of version control and restrict file permissions.

### 4. Content-creation skills (data analysis, presentation, spreadsheet, website)

The task-delivery skills (`data_analysis`, `presentation`, `spreadsheet`, `website`) use only local libraries (pandas, openpyxl, matplotlib, python-pptx). No API keys or credentials are required; outputs are written to paths you specify in the workspace or data directory.

### 5. Flask Debug Mode (Optional, Production)

```bash
# Disable debug mode for production
export FLASK_DEBUG="False"

# Windows PowerShell
$env:FLASK_DEBUG="False"
```

---

## Security Features Enabled

### 1. API Authentication
- All `/api/*` endpoints require API key
- Invalid keys return 403 Forbidden
- Keys validated on every request

### 2. File System and Path Sandboxing
Path access is restricted across multiple skills using the same allowed roots (workspace and data directories from settings or environment).

**filesystem_skill**
- **Allowed roots:** When controller/settings are available, uses `system.workspace_dir` and `system.data_dir` from settings (aligned with `path_sandbox`). Otherwise falls back to `viki/data/`, `viki/workspace/`, `~/Documents`, `~/Desktop`.
- **Blocked:** `C:\Windows`, `C:\Program Files`, `/etc`, `/usr`, `/bin`, `/sbin`, `/boot`, `/sys`, `/proc`.
- Path traversal is blocked; paths are normalized with `os.path.realpath()`.

**dev_tools, whisper, pdf, data_analysis**
- File read/write paths are validated against the same allowed roots (workspace_dir, data_dir). Access outside allowed directories returns "Access denied: path is outside allowed directories".

**Protection:**
- Path traversal attempts (`..\..`) are blocked
- Paths normalized with `os.path.realpath()`
- Access outside sandbox returns error

### 3. Action and Request Validation
- **validate_action:** Every skill execution (confirm path and ReAct path) is checked by `safety.validate_action(skill_name, params)` before running. Prohibited patterns and admin-file access are blocked; blocked requests return "Action blocked by safety policy."
- **Prompt injection mitigation:** Incoming prompts are sanitized: blocklisted phrases (e.g. jailbreak-style instructions) are stripped or replaced. See `safety.injection_blocklist` in code.
- **Optional LLM security scan:** Set `system.security_scan_requests: true` in `viki/config/settings.yaml` to run an LLM-based security scan before deliberation. Adds latency; recommended for high-assurance deployments.

### 4. Command Injection and Shell Safety
- PowerShell commands use proper escaping
- System control uses explicit process creation (no `shell=True`)
- **Shell skill:** Commands containing `;`, `&&`, `||`, or `|` are classified as at least **destructive** (require confirmation) to prevent chaining safe + destructive in one string.
- Input validation rejects dangerous characters where applicable

### 5. Secret Redaction
- **Output:** `safety.sanitize_output()` redacts API keys and tokens (e.g. `sk-...`, Bearer JWTs, `xoxb-`, `ghp_`) in model output before it is shown or stored.
- **Logging:** User input and skill params (e.g. shell `command`, `path`) are logged via `safe_for_log()` (redact + truncate) to avoid leaking secrets in logs.

### 6. SSRF Protection
The `research_skill` now validates URLs:

**Blocked:**
- Private IP ranges (10.x.x.x, 192.168.x.x, 172.16.x.x)
- Loopback addresses (127.0.0.1, localhost)
- Cloud metadata endpoints (169.254.169.254)
- Non-HTTP protocols (file://, ftp://, etc.)

**Enforced:**
- SSL/TLS verification enabled
- Only http:// and https:// allowed

### 7. Reflex Security
Cached reflex actions now undergo:
- Capability permission checks
- Safety validation
- Shadow mode enforcement
- Falls back to full deliberation if blocked

---

### CLI Setup

```bash
# Clone and install
git clone https://github.com/Orythix/viki.git
cd viki

# Create .env file (DO NOT commit to git!)
cat > .env << EOF
VIKI_API_KEY=your-secure-api-key-here
VIKI_ADMIN_SECRET=your-secure-admin-secret-here
EOF

# Install dependencies
pip install -e .

# Run CLI
viki
```

---

## Migration Notes

1. **CLI-First Architecture**
   - The React Dashboard and Flask REST API have been removed to reduce surface area and dependency overhead.
   - **Action:** Use the `viki` command or `python viki/bootstrap.py` for all interactions.

### Non-Breaking Changes

- Debounced file writes (internal optimization)
- Async I/O improvements (performance enhancement)
- Reflex security checks (security hardening)
- SSRF protection (security hardening)

---

## Testing

### Run Tests

```bash
cd viki
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_viki_integration.py::TestVIKIIntegration::test_basic_request -v
```

### Manual Security Testing

```bash
# Test API authentication
curl http://127.0.0.1:5000/api/health  # Should fail (401)
curl -H "Authorization: Bearer wrong-key" http://127.0.0.1:5000/api/health  # Should fail (403)
curl -H "Authorization: Bearer $VIKI_API_KEY" http://127.0.0.1:5000/api/health  # Should succeed

# Test path traversal protection
# In VIKI CLI:
# > read file ../../etc/passwd
# Expected: "Access denied: outside allowed directories"

# Test SSRF protection
# In VIKI CLI:
# > research http://169.254.169.254/latest/meta-data/
# Expected: "URL validation failed: Access to cloud metadata endpoints not allowed"
```

---

## Support

For issues or questions:
1. Check logs in `viki/data/viki.log`
2. Review `CHANGELOG.md` for release changes
3. See `ARCHITECTURE_REFACTOR.md` for future plans
4. Use `logs/viki.log` and your host metrics stack for monitoring

---

## Third-party code and MCP

When integrating external agent or IDE codebases as **design reference only**, prefer reimplementation against public specifications (for example the [Model Context Protocol](https://modelcontextprotocol.io)) and VIKI’s existing modules. Do not copy proprietary or license-incompatible sources into this repository without confirming rights and compatibility with Apache-2.0. VIKI’s MCP client (`viki/integrations/mcp_client.py`) uses the official `mcp` Python SDK optional extra (`pip install "viki-sdi[mcp]"`).

## Compliance Notes

**CFAA Compliance:** Security skill now enforces local network-only scanning.

**Data Protection:** File system sandboxing prevents unauthorized access to sensitive files.

**API Security:** Authentication prevents unauthorized control of VIKI.

**Audit Trail:** Admin actions logged to `data/admin_logs.txt`.
