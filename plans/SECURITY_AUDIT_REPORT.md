# VIKI Security & Quality Audit Report

**Audit Date:** 2026-02-15  
**Version Audited:** 7.2.0 (per README.md)  
**Auditor:** Kilo Code Architect Mode  
**Status:** FIXES IMPLEMENTED  

**Note (2026-02-17):** Additional security focus implemented in 7.3.0: validate_action before every skill run, path sandbox for dev_tools/whisper/PDF/data_analysis, secret redaction, prompt injection blocklist, shell chaining as destructive, optional scan_request, filesystem_skill roots from settings. See CHANGELOG 7.3.0 and viki/SECURITY_SETUP.md.

---

## Executive Summary

This audit identified **27 issues** across security vulnerabilities, logical inconsistencies, and code quality concerns. The most critical findings involve network exposure misconfiguration, weak command filtering, and missing rate limiting.

**All CRITICAL and HIGH severity issues have been fixed.**

---

## Remediation Status

| Severity | Total | Fixed | Remaining |
| -------- | ----- | ----- | --------- |
| CRITICAL | 3     | 3     | 0         |
| HIGH     | 5     | 5     | 0         |
| MEDIUM   | 8     | 3     | 5         |
| LOW      | 6     | 0     | 6         |
| INFO     | 5     | 0     | 5         |

---

## Severity Classification

| Severity     | Description                                          |
| ------------ | ---------------------------------------------------- |
| ~~CRITICAL~~ | ~~Immediate exploitation risk; requires urgent fix~~ |
| ~~HIGH~~     | ~~Significant security risk; fix within days~~       |
| MEDIUM       | Moderate risk; fix within weeks                      |
| LOW          | Minor issues; fix when convenient                    |
| INFO         | Recommendations for improvement                      |

---

## ~~CRITICAL~~ Severity Issues (FIXED)

### ~~CRIT-001: API Server Binds to All Network Interfaces~~

**Status:** FIXED  
**Location:** [`viki/api/server.py:329`](viki/api/server.py:329)

**Original Finding:**

```python
app.run(debug=debug_mode, host='0.0.0.0', port=5000)
```

**Fix Applied:**

```python
app.run(debug=debug_mode, host='127.0.0.1', port=5000)
```

---

### ~~CRIT-002: CORS Allows All Origins~~

**Status:** FIXED  
**Location:** [`viki/api/server.py:27-54`](viki/api/server.py:27)

**Original Finding:**

```python
response.headers['Access-Control-Allow-Origin'] = '*'
```

**Fix Applied:**

```python
ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5000',
    'http://127.0.0.1:5000',
]
# Plus environment variable for custom origins

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    # Added security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response
```

---

### ~~CRIT-003: Shell Skill Has Trivially Bypassable Forbidden Pattern List~~

**Status:** FIXED  
**Location:** [`viki/skills/builtins/shell_skill.py`](viki/skills/builtins/shell_skill.py)

**Original Finding:**

```python
forbidden = ["format ", "rm -rf", "del /s /q c:", "rd /s /q c:"]
```

**Fix Applied:**

- Implemented allowlist-based approach with `SAFE_PATTERNS` for read-only commands
- Added `DESTRUCTIVE_PATTERNS` requiring explicit confirmation
- Added `FORBIDDEN_PATTERNS` that are always blocked
- Added command classification: `safe`, `destructive`, `forbidden`, `unknown`
- Added logging of all shell executions

---

## ~~HIGH~~ Severity Issues (FIXED)

### ~~HIGH-001: No Rate Limiting on API Endpoints~~

**Status:** FIXED  
**Location:** [`viki/api/server.py:56-109`](viki/api/server.py:56)

**Fix Applied:**

```python
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        # In-memory rate limiter with thread-safe locking

general_limiter = RateLimiter(max_requests=100, window_seconds=60)
chat_limiter = RateLimiter(max_requests=20, window_seconds=60)

@app.before_request
def check_rate_limit():
    # Apply rate limiting to all API requests
```

---

### ~~HIGH-002: SSRF Protection Can Be Bypassed~~

**Status:** FIXED  
**Location:** [`viki/skills/builtins/research_skill.py:122-161`](viki/skills/builtins/research_skill.py:122)

**Fix Applied:**

- Added IPv6 loopback and private address blocking
- Added DNS rebinding protection (verify IP doesn't change during request)
- Added URL-encoded hostname detection
- Added suspicious TLD blocking (.local, .internal, etc.)
- Added AWS IPv6 metadata endpoint blocking

---

### ~~HIGH-003: Evolution Engine Writes Executable Code~~

**Status:** FIXED  
**Location:** [`viki/core/evolution.py:268-341`](viki/core/evolution.py:268)

**Fix Applied:**
Enhanced `_validate_skill_code()` to detect:

- Dangerous imports (subprocess, os.system, eval, exec, etc.)
- Dangerous function calls (eval, exec, compile, **import**, open)
- Dangerous attribute access (**globals**, **builtins**, etc.)
- Dangerous method overrides (**reduce**, **getstate**)
- Suspicious string patterns in code
- Import chain analysis

---

### ~~HIGH-004: API Key Fallback Generates Temporary Key~~

**Status:** FIXED  
**Location:** [`viki/api/server.py:44-60`](viki/api/server.py:44)

**Fix Applied:**

```python
API_KEY = os.getenv('VIKI_API_KEY')
if not API_KEY:
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    if debug_mode:
        API_KEY = "dev-key-for-testing-only"
        viki_logger.warning("Using development API key. NOT FOR PRODUCTION USE.")
    else:
        raise RuntimeError(
            "VIKI_API_KEY environment variable must be set for production use."
        )
```

---

### ~~HIGH-005: Reflex Action Recursive Call Risk~~

**Status:** FIXED  
**Location:** [`viki/core/controller.py:92-94`](viki/core/controller.py:92)

**Fix Applied:**

```python
# Added recursion depth tracking
self._reflex_recursion_depth = 0
self._max_reflex_recursion = 3

# In reflex action fallback:
self._reflex_recursion_depth += 1
if self._reflex_recursion_depth > self._max_reflex_recursion:
    return "Safety: Maximum reflex retry depth exceeded."
```

---

## MEDIUM Severity Issues (PARTIALLY FIXED)

### ~~MED-001: Path Traversal Protection Has TOCTOU Race Condition~~

**Status:** REMAINS OPEN (requires deeper filesystem changes)  
**Location:** [`viki/skills/builtins/filesystem_skill.py:51-70`](viki/skills/builtins/filesystem_skill.py:51)

**Recommendation:** Use `os.open()` with `O_NOFOLLOW` flag on Unix systems.

---

### ~~MED-002: Admin Secret Fallback Generates Random Secret~~

**Status:** REMAINS OPEN  
**Location:** [`viki/core/super_admin.py:15-23`](viki/core/super_admin.py:15)

**Recommendation:** Same as HIGH-004 - require explicit configuration in production.

---

### ~~MED-003: Missing Input Validation on API Endpoints~~

**Status:** FIXED  
**Location:** [`viki/api/server.py:139-165`](viki/api/server.py:139)

**Fix Applied:**

```python
MAX_MESSAGE_LENGTH = 10000
MIN_MESSAGE_LENGTH = 1

def validate_message(message: str) -> tuple[bool, str]:
    # Validates message length, type, null bytes
```

---

### ~~MED-004: SQLite Database No Thread Safety Guarantee~~

**Status:** FIXED  
**Location:** [`viki/core/memory/__init__.py:17-30`](viki/core/memory/__init__.py:17)

**Fix Applied:**

```python
import threading
self._lock = threading.RLock()  # Reentrant lock

# All database operations now wrapped with:
with self._lock:
    # database operations
```

---

### ~~MED-005: Error Messages Expose Internal Details~~

**Status:** REMAINS OPEN  
**Location:** [`viki/api/server.py`](viki/api/server.py)

**Recommendation:** Ensure log files are properly secured.

---

### ~~MED-006: No Audit Trail for Capability Checks~~

**Status:** REMAINS OPEN  
**Location:** [`viki/core/capabilities.py:80-118`](viki/core/capabilities.py:80)

**Recommendation:** Implement append-only audit logging.

---

### ~~MED-007: Evolution Auto-Approval After 3 Successes~~

**Status:** FIXED  
**Location:** [`viki/core/evolution.py:126-140`](viki/core/evolution.py:126)

**Fix Applied:**

```python
# REMOVED: Auto-approval after 3 successes
# Now just logs the success streak for user review
if m["success_count"] >= 3:
    viki_logger.info(f"Evolution: Mutation {m['id']} has {m['success_count']} successes. Ready for manual approval via /approve {m['id']}")
```

---

### ~~MED-008: Missing HTTPS Enforcement~~

**Status:** REMAINS OPEN  
**Location:** [`viki/api/server.py`](viki/api/server.py)

**Recommendation:** Add Flask-Talisman for HTTPS enforcement.

---

## LOW Severity Issues (NOT FIXED)

All LOW severity issues remain open for future improvement:

- LOW-001: Version mismatch in documentation
- LOW-002: Dead code (commented imports)
- LOW-003: Inconsistent error handling patterns
- LOW-004: Hardcoded values scattered throughout
- LOW-005: Missing type hints
- LOW-006: No graceful degradation for LLM unavailability

---

## Informational Recommendations (NOT IMPLEMENTED)

All INFO recommendations remain open:

- INFO-001: Implement Content Security Policy
- INFO-002: Add request signing
- INFO-003: Implement session management
- INFO-004: Add health check dependencies
- INFO-005: Document security architecture

---

## Files Modified

| File                                     | Changes                                                                                |
| ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `viki/api/server.py`                     | CORS allowlist, rate limiting, API key validation, input validation, localhost binding |
| `viki/skills/builtins/shell_skill.py`    | Allowlist-based command filtering, destructive pattern detection                       |
| `viki/skills/builtins/research_skill.py` | Enhanced SSRF protection for IPv6, DNS rebinding                                       |
| `viki/core/evolution.py`                 | Strengthened code validation, removed auto-approval                                    |
| `viki/core/controller.py`                | Recursion depth tracking for reflex actions                                            |
| `viki/core/memory/__init__.py`           | Thread-safe SQLite operations                                                          |

---

## Conclusion

All **CRITICAL** and **HIGH** severity security issues have been addressed. The remaining **MEDIUM** and **LOW** severity issues should be addressed as part of ongoing security hardening efforts.

**Key Security Improvements:**

1. API server now binds to localhost only (127.0.0.1)
2. CORS uses explicit origin allowlist
3. Shell commands use allowlist-based filtering
4. Rate limiting prevents abuse
5. SSRF protection handles IPv6 and DNS rebinding
6. Evolution engine has stronger code validation
7. API key required in production mode
8. Reflex recursion depth limited
9. SQLite operations are thread-safe
10. Input validation on API endpoints

---

**Audit Complete. Fixes Implemented.**
