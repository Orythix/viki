# VIKI Security Setup Guide

**Last updated:** 2026-02-14

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

**Usage:**
```bash
# All API requests must include the key
curl -H "Authorization: Bearer your-generated-key-here" \
  http://127.0.0.1:5000/api/health
```

**Dashboard and Hologram Face UI:** The React app (dashboard and hologram voice view) must send the same API key. Set `VITE_VIKI_API_KEY` in `ui/.env` (or your build environment) to the same value as `VIKI_API_KEY`. See [ui/README.md](../../ui/README.md) for details.

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

### 3. Flask Debug Mode (Optional, Production)

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

### 2. File System Sandboxing
The `filesystem_skill` now restricts access to:

**Allowed Directories:**
- `viki/data/`
- `viki/workspace/`
- `~/Documents`
- `~/Desktop`

**Blocked Directories:**
- `C:\Windows`
- `C:\Program Files`
- `/etc`, `/usr`, `/bin`, `/sbin`, `/boot`, `/sys`, `/proc`

**Protection:**
- Path traversal attempts (`..\..`) are blocked
- Paths normalized with `os.path.realpath()`
- Access outside sandbox returns error

### 3. Command Injection Prevention
- PowerShell commands use proper escaping
- System control uses explicit process creation (no `shell=True`)
- Input validation rejects dangerous characters (`;`, `&`, `|`, `$`, `` ` ``)

### 4. SSRF Protection
The `research_skill` now validates URLs:

**Blocked:**
- Private IP ranges (10.x.x.x, 192.168.x.x, 172.16.x.x)
- Loopback addresses (127.0.0.1, localhost)
- Cloud metadata endpoints (169.254.169.254)
- Non-HTTP protocols (file://, ftp://, etc.)

**Enforced:**
- SSL/TLS verification enabled
- Only http:// and https:// allowed

### 5. Reflex Security
Cached reflex actions now undergo:
- Capability permission checks
- Safety validation
- Shadow mode enforcement
- Falls back to full deliberation if blocked

---

## Quick Start

### Development Setup

```bash
# Clone and install
git clone <repository>
cd VIKI

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export VIKI_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export VIKI_ADMIN_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Save your keys!
echo "API Key: $VIKI_API_KEY"
echo "Admin Secret: $VIKI_ADMIN_SECRET"

# Run CLI
python viki/main.py

# Run API server (separate terminal)
python viki/api/server.py
```

### Production Setup

```bash
# Create .env file (DO NOT commit to git!)
cat > .env << EOF
VIKI_API_KEY=your-secure-api-key-here
VIKI_ADMIN_SECRET=your-secure-admin-secret-here
FLASK_DEBUG=False
EOF

# Load environment
source .env  # or use dotenv in Python

# Run with production settings
python viki/api/server.py
```

---

## Migration Notes

### Breaking Changes

1. **API Authentication Required**
   - Old: No authentication
   - New: Must provide API key in Authorization header
   - **Action:** Update all API clients to include key

2. **File System Access Restricted**
   - Old: Unrestricted file access
   - New: Sandboxed to specific directories
   - **Action:** Ensure file operations target allowed directories

3. **Admin Secret Changed**
   - Old: Hardcoded in admin.yaml
   - New: Must be set via environment variable
   - **Action:** Set `VIKI_ADMIN_SECRET` before using admin commands

4. **Server Binding Changed**
   - Old: Binds to `0.0.0.0:5000` (all interfaces)
   - New: Binds to `127.0.0.1:5000` (localhost only)
   - **Action:** Use reverse proxy (nginx, etc.) for external access

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
2. Review `IMPLEMENTATION_SUMMARY.md` for changes
3. See `ARCHITECTURE_REFACTOR.md` for future plans
4. See `OBSERVABILITY.md` for monitoring setup

---

## Compliance Notes

**CFAA Compliance:** Security skill now enforces local network-only scanning.

**Data Protection:** File system sandboxing prevents unauthorized access to sensitive files.

**API Security:** Authentication prevents unauthorized control of VIKI.

**Audit Trail:** Admin actions logged to `data/admin_logs.txt`.
