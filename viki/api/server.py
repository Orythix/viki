"""
VIKI API Server
Provides RESTful endpoints for the React dashboard
"""
from flask import Flask, request, jsonify, g, Response, stream_with_context
from flask_cors import CORS
from datetime import datetime
import sys
import os
import asyncio
import json
from functools import wraps
import secrets
import uuid
import re
from dotenv import load_dotenv
import threading
import time
import queue
from typing import Any, Dict

load_dotenv()

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController
from viki.core.safety import safe_for_log
from viki.config.logger import viki_logger
from viki.config.resolve import get_soul_path
from viki.api.events import get_event_bus

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Project root (parent of viki package) for data/uploads
project_root = os.path.dirname(base_dir)
UPLOAD_DIR = os.path.join(project_root, "data", "uploads")
UPLOAD_MAX_MB = int(os.getenv("VIKI_UPLOAD_MAX_MB", "10"))
UPLOAD_MAX_BYTES = UPLOAD_MAX_MB * 1024 * 1024
# Block executable and script extensions
UPLOAD_BLOCKED_EXTENSIONS = {".exe", ".sh", ".bat", ".cmd", ".ps1", ".py", ".js", ".ts"}

settings_path = os.path.join(base_dir, "config", "settings.yaml")
soul_path = get_soul_path(settings_path)
SESSION_HEADER = "X-Session-Id"
_controller = None
_controller_lock = threading.Lock()


def get_controller() -> VIKIController:
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = VIKIController(settings_path=settings_path, soul_path=soul_path)
                try:
                    _controller.attach_mcp_skills_sync()
                except Exception as e:
                    viki_logger.debug(f"MCP attach skipped: {e}")
    return _controller


def get_session_id() -> str:
    raw = (request.headers.get(SESSION_HEADER) or "").strip()
    if raw:
        return re.sub(r"[^A-Za-z0-9._-]", "_", raw)[:128] or "default"
    return "default"


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _safe_extension(filename: str) -> str:
    """Return lowercased extension including dot, or empty string."""
    _, ext = os.path.splitext(filename)
    return (ext or "").lower()


def _save_uploaded_file(file) -> tuple:
    """
    Save an uploaded file to UPLOAD_DIR. Returns (absolute_path, error_message).
    On success error_message is None.
    """
    if not file or not file.filename:
        return None, "No file"
    ext = _safe_extension(file.filename)
    if ext in UPLOAD_BLOCKED_EXTENSIONS:
        return None, f"File type not allowed: {ext}"
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > UPLOAD_MAX_BYTES:
        return None, f"File too large (max {UPLOAD_MAX_MB} MB)"
    safe_name = re.sub(r"[^\w\-\.]", "_", file.filename)
    if len(safe_name) > 200:
        safe_name = safe_name[:200] + ext
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = os.path.join(UPLOAD_DIR, unique_name)
    try:
        _ensure_upload_dir()
        file.save(dest_path)
        return os.path.abspath(dest_path), None
    except Exception as e:
        viki_logger.warning(f"Upload save failed: {e}")
        return None, str(e)

app = Flask(__name__)

# P1: optional flask-sock based WebSocket. Falls back to no-op if not installed.
_sock = None
try:
    from flask_sock import Sock  # type: ignore
    _sock = Sock(app)
except Exception as e:
    viki_logger.debug("flask_sock not available; /ws disabled (%s).", e)

# --- SECURITY FIX: HIGH-004 - Require API key in production ---
API_KEY = os.getenv('VIKI_API_KEY')
if not API_KEY:
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    if debug_mode:
        # Only allow fallback in debug mode for development
        API_KEY = "dev-key-for-testing-only"
        viki_logger.warning("Using development API key. NOT FOR PRODUCTION USE.")
        viki_logger.warning("Set VIKI_API_KEY environment variable for secure operation.")
    else:
        # In production, fail fast if no API key is configured
        raise RuntimeError(
            "VIKI_API_KEY environment variable must be set for production use. "
            "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

# --- SECURITY FIX: CRIT-002 - Explicit CORS origin allowlist ---
# Configure allowed origins explicitly instead of wildcard
ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5000',
    'http://127.0.0.1:5000',
]

# Add any custom origins from environment
custom_origins = os.getenv('VIKI_CORS_ORIGINS', '')
if custom_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in custom_origins.split(',') if o.strip()])

CORS(app, origins=ALLOWED_ORIGINS)

@app.after_request
def add_cors_headers(response):
    """Security-hardened CORS headers - only allow explicit origins."""
    origin = request.headers.get('Origin')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Session-Id'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# --- SECURITY FIX: HIGH-001 - Rate limiting implementation ---
# Simple in-memory rate limiter (for production, use Redis or flask-limiter)
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests = {}  # {ip: [(timestamp, ...)]}
        self._lock = threading.Lock()
    
    def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining_requests)."""
        current_time = time.time()
        
        with self._lock:
            # Clean old requests
            if client_ip in self._requests:
                self._requests[client_ip] = [
                    t for t in self._requests[client_ip]
                    if current_time - t < self.window_seconds
                ]
            else:
                self._requests[client_ip] = []
            
            # Check limit
            request_count = len(self._requests[client_ip])
            if request_count >= self.max_requests:
                return False, 0
            
            # Record this request
            self._requests[client_ip].append(current_time)
            return True, self.max_requests - request_count - 1

# Create rate limiters for different endpoint types
general_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100 req/min
chat_limiter = RateLimiter(max_requests=20, window_seconds=60)     # 20 req/min for chat

@app.before_request
def check_rate_limit():
    """Apply rate limiting to all API requests."""
    if request.path.startswith('/api/'):
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # Use stricter limiter for chat endpoint
        if request.path == '/api/chat':
            limiter = chat_limiter
        else:
            limiter = general_limiter
        
        allowed, remaining = limiter.is_allowed(client_ip)
        if not allowed:
            return jsonify({
                'error': 'Rate limit exceeded',
                'retry_after': 60
            }), 429

@app.before_request
def log_request_info():
    g.request_id = uuid.uuid4().hex[:12]
    g.viki_session = (request.headers.get(SESSION_HEADER) or "").strip()[:64] or "-"
    viki_logger.debug(
        "request_id=%s session=%s %s %s",
        getattr(g, "request_id", "?"),
        getattr(g, "viki_session", "?"),
        request.method,
        request.path,
    )
    if request.path.startswith('/api/'):
        auth = request.headers.get('Authorization', 'Missing')
        viki_logger.debug(f"Auth Header: {auth[:15] if len(auth) > 15 else auth}...")

def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for API key in header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401
        
        # Support "Bearer <token>" or just "<token>"
        token = auth_header.replace('Bearer ', '').strip()
        
        # Robust comparison with stripping
        target_key = str(API_KEY).strip()
        if token != target_key:
            viki_logger.warning(f"Invalid API key attempt. Received len: {len(token)}, Expected len: {len(target_key)}")
            return jsonify({'error': 'Invalid API key'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def async_route(f):
    """Decorator to properly handle async routes in Flask."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

# --- SECURITY FIX: MED-003 - Input validation ---
MAX_MESSAGE_LENGTH = 10000  # Maximum message length in characters
MIN_MESSAGE_LENGTH = 1      # Minimum message length

def validate_message(message: str) -> tuple[bool, str]:
    """Validate user input message.
    
    Returns: (is_valid, error_message)
    """
    if not message:
        return False, "Message cannot be empty"
    
    if not isinstance(message, str):
        return False, "Message must be a string"
    
    # Strip whitespace for length check
    stripped = message.strip()
    if len(stripped) < MIN_MESSAGE_LENGTH:
        return False, "Message cannot be empty or whitespace only"
    
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters"
    
    # Check for null bytes (potential injection)
    if '\x00' in message:
        return False, "Message contains invalid characters"
    
    return True, ""

@app.route('/ping', methods=['GET'])
def ping():
    viki_logger.info("PING HIT")
    return "pong"

@app.route('/api/health', methods=['GET'])
@require_api_key
def health():
    try:
        controller = get_controller()
        tools = list(controller.skill_registry.skills.keys()) if hasattr(controller, 'skill_registry') and controller.skill_registry else []
        return jsonify({
            'status': 'online',
            'version': controller.soul.config.get('version', 'Unknown'),
            'name': controller.soul.config.get('name', 'VIKI'),
            'persona': getattr(controller, 'persona', 'sovereign'),
            'tagline': controller.soul.config.get('tagline') or controller.soul.config.get('positioning', ''),
            'differentiators': controller.get_differentiators(),
            'tools': tools,
            'runtime_health': controller.get_runtime_health() if hasattr(controller, 'get_runtime_health') else {},
        })
    except Exception as e:
        viki_logger.error(
            "Health check error (request_id=%s): %s",
            getattr(g, "request_id", "?"),
            e,
            exc_info=True,
        )
        return jsonify({'error': 'Health check failed. See server logs.'}), 500

@app.route('/api/chat', methods=['POST'])
@require_api_key
@async_route
async def chat():
    """Process chat messages asynchronously. Accepts JSON or multipart/form-data (message + files)."""
    try:
        controller = get_controller()
        session_id = get_session_id()
        viki_logger.info("API: Chat request received")
        content_type = request.content_type or ""
        attachment_paths = []

        if "multipart/form-data" in content_type:
            user_input = (request.form.get("message") or "").strip()
            # Multiple files can be under key "files"
            uploaded_files = request.files.getlist("files") if "files" in request.files else []
            for f in uploaded_files:
                path, err = _save_uploaded_file(f)
                if err:
                    return jsonify({'error': err}), 400
                if path:
                    attachment_paths.append(path)
        else:
            data = request.json
            if not data:
                return jsonify({'error': 'Invalid JSON body'}), 400
            user_input = data.get('message', '')

        if attachment_paths and not str(user_input or "").strip():
            user_input = "Please analyze the attached file(s)."

        # --- SECURITY FIX: MED-003 - Input validation ---
        is_valid, error_msg = validate_message(user_input)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        viki_logger.info(
            "API: Processing user input (request_id=%s session=%s): '%s'...",
            getattr(g, "request_id", "?"),
            getattr(g, "viki_session", "?"),
            safe_for_log(user_input),
        )
        timeout_sec = controller.settings.get('system', {}).get('request_timeout_seconds', 0)
        if timeout_sec <= 0:
            timeout_sec = 600  # Ceiling when disabled so one stuck request does not hold worker indefinitely
        try:
            response = await asyncio.wait_for(
                controller.process_request(
                    user_input,
                    attachment_paths=attachment_paths if attachment_paths else None,
                    session_id=session_id
                ),
                timeout=float(timeout_sec)
            )
        except asyncio.TimeoutError:
            viki_logger.warning(f"API: Request timed out after {timeout_sec}s")
            return jsonify({'error': 'Request timed out. Try a shorter or simpler request.'}), 504
        viki_logger.info("API: Response generated successfully")

        payload = {
            'response': response,
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
        }
        meta = controller.get_last_response_meta(session_id=session_id)
        if meta:
            payload['subtasks'] = meta.get('subtasks')
            payload['total_steps'] = meta.get('total_steps')
        return jsonify(payload)
    except Exception as e:
        viki_logger.error(f"API chat error: {e}", exc_info=True)
        # Don't expose internal error details to client
        return jsonify({'error': "An internal error occurred while processing your request."}), 500

@app.route('/api/chat/stream', methods=['POST'])
@require_api_key
def chat_stream():
    """
    Phase 6: Server-Sent Events streaming chat.

    Emits one event per "stage" (route, status, partial token, final response)
    so the UI can render token-by-token. Falls back to a single 'final' event
    if the controller cannot produce intermediate output.
    """
    try:
        controller = get_controller()
        session_id = get_session_id()
        data = request.get_json(silent=True) or {}
        user_input = (data.get("message") or "").strip()
        is_valid, error_msg = validate_message(user_input)
        if not is_valid:
            return jsonify({"error": error_msg}), 400

        @stream_with_context
        def gen():
            yield _sse("status", {"phase": "received", "session_id": session_id})

            # P0 fix: real per-event streaming. Run controller.process_request
            # in a worker thread that pushes (kind, payload) tuples into a
            # thread-safe queue; the generator drains the queue and yields
            # each event as it arrives. A sentinel terminates the loop.
            event_queue: queue.Queue = queue.Queue()
            SENTINEL = object()
            result_holder: Dict[str, Any] = {"response": None, "error": None}

            def on_event(kind: str, payload):
                try:
                    event_queue.put((kind, payload))
                except Exception:
                    pass

            def worker():
                try:
                    response = asyncio.run(
                        controller.process_request(
                            user_input, session_id=session_id, on_event=on_event
                        )
                    )
                    result_holder["response"] = response
                except Exception as e:
                    result_holder["error"] = str(e)
                    viki_logger.error(f"chat_stream worker error: {e}", exc_info=True)
                finally:
                    event_queue.put(SENTINEL)

            t = threading.Thread(target=worker, name="chat-stream", daemon=True)
            t.start()

            try:
                while True:
                    try:
                        item = event_queue.get(timeout=30.0)
                    except queue.Empty:
                        # Heartbeat keeps proxies/load-balancers from closing the connection.
                        yield _sse("ping", {"ts": datetime.now().isoformat()})
                        continue
                    if item is SENTINEL:
                        break
                    kind, payload = item
                    yield _sse(kind, {"payload": payload})

                if result_holder["error"]:
                    yield _sse("error", {"error": "Internal streaming error."})
                else:
                    meta = controller.get_last_response_meta(session_id=session_id) or {}
                    yield _sse(
                        "final",
                        {
                            "response": result_holder["response"],
                            "subtasks": meta.get("subtasks"),
                            "total_steps": meta.get("total_steps"),
                            "cognitive_route": meta.get("cognitive_route"),
                        },
                    )
            except GeneratorExit:
                viki_logger.debug("chat_stream client disconnected.")
                raise
            except Exception as e:
                viki_logger.error(f"chat_stream generator error: {e}", exc_info=True)
                yield _sse("error", {"error": "Internal streaming error."})
            finally:
                yield _sse("done", {})

        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        return Response(gen(), headers=headers)
    except Exception as e:
        viki_logger.error(f"chat_stream error: {e}", exc_info=True)
        return jsonify({"error": "An internal error occurred while opening stream."}), 500


def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data, default=str) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


@app.route('/api/memory', methods=['GET'])
@require_api_key
def get_memory():
    """Retrieve conversation memory"""
    try:
        controller = get_controller()
        session_id = get_session_id()
        # Use get_context to fetch latest messages from DB or ephemeral memory
        messages = controller.memory.working.get_trace(session_id=session_id)
        return jsonify({
            'messages': messages,
            'limit': controller.memory.working.max_turns,
            'session_id': session_id,
        })
    except Exception as e:
        viki_logger.error(
            "Memory retrieval error (request_id=%s): %s",
            getattr(g, "request_id", "?"),
            e,
            exc_info=True,
        )
        return jsonify({'error': 'Failed to load memory.'}), 500

@app.route('/api/memory', methods=['DELETE'])
@require_api_key
def clear_memory():
    """Clear conversation memory"""
    controller = get_controller()
    controller.memory.working.clear_trace(session_id=get_session_id())
    return jsonify({'status': 'cleared'})

@app.route('/api/skills', methods=['GET'])
@require_api_key
def get_skills():
    """List all registered skills"""
    controller = get_controller()
    skills = []
    for name, skill in controller.skill_registry.skills.items():
        skills.append({
            'name': name,
            'description': skill.description if hasattr(skill, 'description') else "No description",
            'triggers': skill.triggers if hasattr(skill, 'triggers') else []
        })
    return jsonify({'skills': skills})

@app.route('/api/models', methods=['GET'])
@require_api_key
def get_models():
    """List available models"""
    controller = get_controller()
    models = []
    if hasattr(controller, 'model_router'):
        for name, model in controller.model_router.models.items():
            models.append({
                'name': name,
                'provider': model.config.get('provider', 'unknown'),
                'capabilities': model.config.get('capabilities', []),
                'description': model.config.get('description', '')
            })
    return jsonify({'models': models})

@app.route('/api/models/performance', methods=['GET'])
@require_api_key
def get_model_performance():
    """Get performance metrics for all models"""
    try:
        controller = get_controller()
        performance = []
        
        if hasattr(controller, 'model_router'):
            for name, model in controller.model_router.models.items():
                # Calculate error rate
                error_rate = 0.0
                if model.call_count > 0:
                    error_rate = model.error_count / model.call_count
                
                performance.append({
                    'name': name,
                    'model_name': model.model_name,
                    'provider': getattr(model, 'provider_name', model.config.get('provider', 'unknown')),
                    'is_cloud': bool(getattr(model, 'is_cloud', lambda: False)()),
                    'capabilities': model.config.get('capabilities', []),
                    'priority': model.config.get('priority', 2),
                    'trust_score': round(model.trust_score, 3),
                    'avg_latency': round(model.avg_latency, 3),
                    'call_count': model.call_count,
                    'error_count': model.error_count,
                    'error_rate': round(error_rate, 3),
                    'cost_per_1k_in': float(getattr(model, 'cost_per_1k_in', 0.0)),
                    'cost_per_1k_out': float(getattr(model, 'cost_per_1k_out', 0.0)),
                    'input_tokens': int(getattr(model, 'input_tokens', 0)),
                    'output_tokens': int(getattr(model, 'output_tokens', 0)),
                    'total_cost_usd': round(float(getattr(model, 'total_cost_usd', 0.0)), 6),
                    'strengths': model.strengths,
                    'weaknesses': model.weaknesses,
                })
            
            # Sort by trust score descending
            performance.sort(key=lambda x: x['trust_score'], reverse=True)
        
        return jsonify({
            'models': performance,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        viki_logger.error(f"Model performance error: {e}", exc_info=True)
        return jsonify({'error': 'Failed to retrieve model performance'}), 500


@app.route('/api/models/budget', methods=['GET'])
@require_api_key
def get_model_budget():
    """Phase 1: cloud cost budget snapshot (daily/per-call caps + circuit breakers)."""
    try:
        controller = get_controller()
        if hasattr(controller, "llm_budget") and controller.llm_budget is not None:
            return jsonify(controller.llm_budget.snapshot())
        return jsonify({"enabled": False})
    except Exception as e:
        viki_logger.error(f"Model budget error: {e}", exc_info=True)
        return jsonify({"error": "Failed to retrieve model budget"}), 500


@app.route('/api/evals', methods=['GET'])
@require_api_key
def get_evals():
    """Phase 2: Capability Index dashboard. Aggregates latest eval runs into one number."""
    try:
        controller = get_controller()
        from viki.core.capability_index import CapabilityIndex

        data_dir = controller.settings.get("system", {}).get("data_dir", "./data")
        results_root = os.path.join(data_dir, "eval_results")
        forge_settings = controller.settings.get("forge", {}) or {}
        min_tasks = int(forge_settings.get("capability_index_min_tasks", 0))
        bootstrap = int(forge_settings.get("capability_index_bootstrap_iters", 0))
        index = CapabilityIndex(
            results_root,
            min_tasks=min_tasks,
            bootstrap_iters=bootstrap,
        ).compute()
        return jsonify(index)
    except Exception as e:
        viki_logger.error(f"Eval index error: {e}", exc_info=True)
        return jsonify({"error": "Failed to compute capability index"}), 500


@app.route('/api/scorecard/segmented', methods=['GET'])
@require_api_key
def get_scorecard_segmented():
    """Phase 5: per-model breakdown of the IntelligenceScorecard."""
    try:
        controller = get_controller()
        return jsonify(controller.scorecard.get_segmented_summary())
    except Exception as e:
        viki_logger.error(f"Scorecard segmented error: {e}", exc_info=True)
        return jsonify({"error": "Failed to compute segmented scorecard"}), 500


@app.route('/api/scorecard/trends', methods=['GET'])
@require_api_key
def get_scorecard_trends():
    """P2: per-model sparkline series + regression detection."""
    try:
        controller = get_controller()
        try:
            points = int(request.args.get("points", 30))
        except (TypeError, ValueError):
            points = 30
        try:
            window = int(request.args.get("window", 10))
        except (TypeError, ValueError):
            window = 10
        try:
            threshold = float(request.args.get("threshold", 0.05))
        except (TypeError, ValueError):
            threshold = 0.05
        return jsonify(controller.scorecard.get_segmented_trends(
            points=points,
            regression_window=window,
            regression_threshold=threshold,
        ))
    except Exception as e:
        viki_logger.error(f"Scorecard trends error: {e}", exc_info=True)
        return jsonify({"error": "Failed to compute scorecard trends"}), 500


@app.route('/api/traces', methods=['GET'])
@require_api_key
def get_traces():
    """Phase 6: in-memory trace records for the OpenTelemetry-style flame graph."""
    try:
        from viki.core.tracing import get_local_spans

        limit = int(request.args.get("limit", 100))
        return jsonify({"spans": get_local_spans(limit=limit)})
    except Exception as e:
        viki_logger.error(f"Trace dump error: {e}", exc_info=True)
        return jsonify({"error": "Failed to read traces"}), 500


@app.route('/api/traces/grouped', methods=['GET'])
@require_api_key
def get_traces_grouped():
    """P1: persistent traces grouped by trace_id with parent/child links for Gantt rendering."""
    try:
        from viki.core.tracing import get_persistent_traces

        limit = int(request.args.get("limit", 50))
        return jsonify({"traces": get_persistent_traces(limit=limit)})
    except Exception as e:
        viki_logger.error(f"Trace group error: {e}", exc_info=True)
        return jsonify({"error": "Failed to read grouped traces"}), 500


@app.route('/api/forge/promotion', methods=['GET'])
@require_api_key
def get_forge_promotion():
    """Phase 5: eval-gated promotion state (current default, history, consecutive passes)."""
    try:
        controller = get_controller()
        learner = getattr(controller, "continuous_learner", None)
        if learner is None:
            return jsonify({"error": "continuous_learner not available"}), 503
        return jsonify(learner.get_status())
    except Exception as e:
        viki_logger.error(f"Promotion state error: {e}", exc_info=True)
        return jsonify({"error": "Failed to read promotion state"}), 500


def _require_admin_secret() -> bool:
    """Forge mutating endpoints require an extra header on top of the API key."""
    expected = os.getenv("VIKI_ADMIN_SECRET", "")
    if not expected:
        return True  # no admin secret configured -> allow
    provided = request.headers.get("X-Admin-Secret", "")
    return bool(provided) and secrets.compare_digest(provided, expected)


@app.route('/api/forge/promote', methods=['POST'])
@require_api_key
def forge_promote():
    """Operator-initiated promotion. Bypasses the consecutive-passes gate."""
    if not _require_admin_secret():
        return jsonify({"error": "admin secret required"}), 403
    data = request.get_json(silent=True) or {}
    model_name = (data.get("model") or "").strip()
    if not model_name:
        return jsonify({"error": "model is required"}), 400
    controller = get_controller()
    learner = getattr(controller, "continuous_learner", None)
    if learner is None or not hasattr(learner, "force_promote"):
        return jsonify({"error": "continuous_learner not available"}), 503
    try:
        result = learner.force_promote(model_name, operator=data.get("operator") or "ui")
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        viki_logger.error(f"force_promote failed: {e}", exc_info=True)
        return jsonify({"error": "force_promote failed"}), 500


@app.route('/api/forge/rollback', methods=['POST'])
@require_api_key
def forge_rollback():
    """Operator-initiated rollback to the previous (or specified) default model."""
    if not _require_admin_secret():
        return jsonify({"error": "admin secret required"}), 403
    data = request.get_json(silent=True) or {}
    model_name = (data.get("model") or "").strip() or None
    controller = get_controller()
    learner = getattr(controller, "continuous_learner", None)
    if learner is None or not hasattr(learner, "force_rollback"):
        return jsonify({"error": "continuous_learner not available"}), 503
    try:
        result = learner.force_rollback(model_name, operator=data.get("operator") or "ui")
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)
    except Exception as e:
        viki_logger.error(f"force_rollback failed: {e}", exc_info=True)
        return jsonify({"error": "force_rollback failed"}), 500

@app.route('/api/world', methods=['GET'])
@require_api_key
def get_world():
    """Get World Engine state (Phase 4)"""
    controller = get_controller()
    state = controller.world.state.model_dump()
    # Summarize graph for lightweight transfer
    state['codebase_graph_summary'] = {
        'count': len(state.get('codebase_graph', {})),
        'active_focus': state.get('active_context', [])
    }
    if 'codebase_graph' in state:
        del state['codebase_graph'] # Too large for full dump
    return jsonify(state)

@app.route('/api/brain', methods=['GET'])
@require_api_key
def get_brain():
    """Get Cognitive State (Signals & Trace)"""
    controller = get_controller()
    session_id = get_session_id()
    router_telemetry: Dict[str, Any] = {}
    if hasattr(controller, "get_router_telemetry"):
        try:
            router_telemetry = controller.get_router_telemetry()
        except Exception:
            router_telemetry = {}
    return jsonify({
        'signals': controller.signals.get_modulation(),
        'trace': controller.internal_trace[-5:] if controller.internal_trace else [],
        'last_thought': controller.memory.working.get_last_thought(session_id=session_id) if hasattr(controller.memory.working, 'get_last_thought') else "",
        'mode': controller.interaction_pace,
        'router_telemetry': router_telemetry,
    })

@app.route('/api/missions', methods=['GET', 'POST'])
@require_api_key
def missions_collection():
    """List autonomous missions (GET) or queue a new one (POST)."""
    controller = get_controller()
    if not hasattr(controller, 'mission_control'):
        if request.method == 'GET':
            return jsonify({'queue': [], 'active': []})
        return jsonify({"error": "MissionControl not initialized"}), 503

    if request.method == 'GET':
        queue = [m.to_dict() for m in controller.mission_control.mission_queue]
        active = [m.to_dict() for m in controller.mission_control.active_missions.values()]
        return jsonify({'queue': queue, 'active': active})

    data = request.get_json(silent=True) or {}
    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({"error": "description is required"}), 400
    try:
        from viki.core.mission_control import MissionType
        m_type_raw = (data.get('type') or 'maintenance').lower()
        try:
            m_type = MissionType(m_type_raw)
        except ValueError:
            m_type = MissionType.MAINTENANCE
        mid = controller.mission_control.add_mission(
            description,
            int(data.get('priority', 50)),
            m_type,
            int(data.get('repeat_interval', 0)),
        )
        return jsonify({"id": mid, "description": description}), 201
    except Exception as e:
        viki_logger.error(f"Mission create failed: {e}", exc_info=True)
        return jsonify({"error": "Failed to queue mission"}), 500


@app.route('/api/missions/<mission_id>', methods=['GET'])
@require_api_key
def get_mission(mission_id):
    controller = get_controller()
    mc = getattr(controller, 'mission_control', None)
    if mc is None:
        return jsonify({"error": "MissionControl not initialized"}), 404
    m = mc.active_missions.get(mission_id)
    if m is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(m.to_dict())


@app.route('/api/missions/<mission_id>/cancel', methods=['POST'])
@require_api_key
def cancel_mission(mission_id):
    controller = get_controller()
    mc = getattr(controller, 'mission_control', None)
    if mc is None:
        return jsonify({"error": "MissionControl not initialized"}), 404
    m = mc.active_missions.get(mission_id)
    if m is None:
        return jsonify({"error": "not found"}), 404
    m.status = "cancelled"
    try:
        mc._save_missions()
    except Exception:
        pass
    return jsonify({"id": mission_id, "status": m.status})


@app.route('/api/missions/<mission_id>/graph', methods=['GET'])
@require_api_key
def mission_graph(mission_id):
    """Return the mission's task graph if one was constructed."""
    controller = get_controller()
    graphs = getattr(controller, 'mission_graphs', None) or {}
    g = graphs.get(mission_id)
    if g is None:
        return jsonify({"mission_id": mission_id, "nodes": [], "edges": []})
    nodes = []
    edges = []
    for nid, n in getattr(g, 'nodes', {}).items():
        nodes.append({
            "id": nid,
            "title": getattr(n, 'title', nid),
            "status": getattr(getattr(n, 'status', None), 'value', str(getattr(n, 'status', ''))),
            "skill": getattr(n, 'skill', None),
        })
        for parent in getattr(n, 'depends_on', []) or []:
            edges.append({"from": parent, "to": nid})
    return jsonify({
        "mission_id": mission_id,
        "goal": getattr(g, 'goal', ''),
        "nodes": nodes,
        "edges": edges,
    })


@app.route('/api/subagents', methods=['GET'])
@require_api_key
def list_subagents():
    controller = get_controller()
    registry = getattr(controller, 'sub_agents', {}) or {}
    out = []
    for sid, agent in registry.items():
        out.append({
            "id": sid,
            "name": getattr(agent, 'name', ''),
            "parent": getattr(agent, 'parent', None),
            "capabilities": sorted(list(getattr(agent, 'capabilities', set()))),
            "is_running": bool(getattr(agent, 'is_running', False)),
            "started_at": getattr(agent, 'started_at', None),
            "finished_at": getattr(agent, 'finished_at', None),
            "error": getattr(agent, 'error', None),
        })
    return jsonify({"subagents": out})


@app.route('/api/subagents/<subagent_id>/cancel', methods=['POST'])
@require_api_key
def cancel_subagent(subagent_id):
    controller = get_controller()
    registry = getattr(controller, 'sub_agents', {}) or {}
    agent = registry.get(subagent_id)
    if agent is None:
        return jsonify({"error": "not found"}), 404
    try:
        task = getattr(agent, '_task', None)
        if task is not None:
            task.cancel()
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"id": subagent_id, "status": "cancelling"})


@app.route('/api/code/search', methods=['GET'])
@require_api_key
def code_search():
    """
    P1: thin REST wrapper over the persistent code-search index.

    Query params:
      q       (required)  search query
      top_k   (optional)  default=8
      action  (optional)  'search' | 'symbol' | 'scan' (default: search)
    """
    controller = get_controller()
    skill = controller.skill_registry.get_skill('code_search') if hasattr(controller, 'skill_registry') else None
    if skill is None:
        return jsonify({"error": "code_search skill not registered"}), 404
    action = (request.args.get('action') or 'search').lower()
    q = request.args.get('q') or ''
    top_k = int(request.args.get('top_k') or 8)
    try:
        if action == 'scan':
            n_files, n_chunks, n_symbols = skill.scan(skill._workspace_dir())
            return jsonify({"n_files": n_files, "n_chunks": n_chunks, "n_symbols": n_symbols})
        if action == 'symbol':
            results = skill.find_symbol(q)
            return jsonify({"symbols": [s.__dict__ for s in results]})
        results = skill.search(q, top_k=top_k)
        return jsonify({"chunks": [r.as_dict() for r in results]})
    except Exception as e:
        viki_logger.error(f"code_search endpoint error: {e}", exc_info=True)
        return jsonify({"error": "code_search failed"}), 500


@app.route('/api/artifacts/<mission_id>', methods=['GET'])
@require_api_key
def get_artifacts_manifest(mission_id):
    """Return the artifact manifest for a mission."""
    controller = get_controller()
    workspace = (controller.settings.get("system") or {}).get("workspace_dir", "./workspace")
    try:
        from viki.core.artifact_manifest import ArtifactManifest
        m = ArtifactManifest.load(mission_id, workspace)
    except Exception as e:
        viki_logger.error(f"manifest load failed: {e}", exc_info=True)
        return jsonify({"error": "manifest load failed"}), 500
    if m is None:
        return jsonify({"error": "manifest not found"}), 404
    return jsonify(m.to_dict())


@app.route('/api/artifacts/<mission_id>/file', methods=['GET'])
@require_api_key
def get_artifact_file(mission_id):
    """
    Stream a single artifact file. The artifact must be listed in the
    mission's manifest and must live inside the workspace dir.
    """
    controller = get_controller()
    workspace_dir = os.path.abspath(
        (controller.settings.get("system") or {}).get("workspace_dir", "./workspace")
    )
    rel = (request.args.get("path") or "").strip()
    if not rel:
        return jsonify({"error": "path required"}), 400
    abs_path = os.path.abspath(rel)
    # Path traversal guard: artifact must be inside workspace_dir.
    if not abs_path.startswith(workspace_dir + os.sep) and abs_path != workspace_dir:
        return jsonify({"error": "path outside workspace"}), 403
    try:
        from viki.core.artifact_manifest import ArtifactManifest
        m = ArtifactManifest.load(mission_id, workspace_dir)
    except Exception:
        m = None
    if m is None:
        return jsonify({"error": "manifest not found"}), 404
    listed = {os.path.abspath(a.path) for a in m.artifacts}
    if abs_path not in listed:
        return jsonify({"error": "artifact not in manifest"}), 404
    if not os.path.isfile(abs_path):
        return jsonify({"error": "file missing on disk"}), 410

    def gen():
        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    fname = os.path.basename(abs_path)
    return Response(
        gen(),
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@app.route('/api/mcp/servers', methods=['GET'])
@require_api_key
def get_mcp_servers():
    """List MCP-connected servers and the tools they expose as VIKI skills."""
    controller = get_controller()
    client = getattr(controller, 'mcp_client', None)
    if client is None:
        return jsonify({
            "enabled": False,
            "servers": [],
            "skill_count": 0,
            "reason": "MCP SDK not installed or no servers configured.",
        })
    tools = client.list_tools() if hasattr(client, 'list_tools') else []
    by_server: Dict[str, list] = {}
    for t in tools:
        by_server.setdefault(t.get('server', '?'), []).append({
            "name": t.get('tool'),
            "description": t.get('description', ''),
        })
    servers = [{"name": name, "tools": tlist} for name, tlist in by_server.items()]
    return jsonify({
        "enabled": True,
        "servers": servers,
        "skill_count": int(getattr(controller, 'mcp_skill_count', 0) or 0),
    })

if _sock is not None:
    @_sock.route('/ws')
    def ws_endpoint(ws):
        """
        Bidirectional channel for live mission/sub-agent events. Auth uses
        the same `?api_key=...` query arg or `X-API-Key` header as REST.
        Inbound messages: JSON with {"action": "subscribe"|"interrupt"|"ping",
        "channels": [...], "target_id": "..."}.
        """
        token = (
            request.headers.get('X-API-Key')
            or request.args.get('api_key')
            or ''
        )
        if not token or not secrets.compare_digest(token, API_KEY or ''):
            ws.send(json.dumps({"event": "error", "data": {"error": "unauthorized"}}))
            return
        bus = get_event_bus()
        sub = bus.subscribe(channels=None)
        try:
            ws.send(json.dumps({"event": "hello", "data": {"sub_id": sub.id}}))

            def _drain():
                while True:
                    try:
                        msg = sub.queue.get(timeout=15.0)
                        ws.send(msg)
                    except queue.Empty:
                        try:
                            ws.send(json.dumps({"event": "ping", "data": {"ts": time.time()}}))
                        except Exception:
                            return
                    except Exception:
                        return

            t = threading.Thread(target=_drain, daemon=True)
            t.start()

            controller = get_controller()
            while True:
                raw = ws.receive(timeout=60)
                if raw is None:
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    msg = {"action": "raw", "payload": raw}
                action = (msg.get("action") or "").lower()
                if action == "ping":
                    ws.send(json.dumps({"event": "pong", "data": {}}))
                elif action == "interrupt":
                    target = msg.get("target_id")
                    sub_agents = getattr(controller, 'sub_agents', {}) or {}
                    agent = sub_agents.get(target)
                    if agent is not None:
                        try:
                            t = getattr(agent, '_task', None)
                            if t is not None:
                                t.cancel()
                        except Exception as e:
                            ws.send(json.dumps({"event": "error", "data": {"error": str(e)}}))
                            continue
                        ws.send(json.dumps({"event": "interrupted", "data": {"id": target}}))
                    else:
                        ws.send(json.dumps({"event": "error", "data": {"error": "not_found"}}))
        finally:
            bus.unsubscribe(sub.id)


if __name__ == '__main__':
    controller = get_controller()
    viki_logger.info("Starting VIKI API Server (ASYNCHRONOUS)...")
    viki_logger.info(f"VIKI Version: {controller.soul.config.get('version', 'Unknown')}")
    viki_logger.info("API available at: http://localhost:5000")
    # SECURITY: Don't log any part of the API key
    viki_logger.info("API Key required for authentication. Key configured: Yes")
    # Disable debug mode in production for security
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    # SECURITY: Default bind to localhost; set FLASK_HOST=0.0.0.0 when running in Docker
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    app.run(debug=debug_mode, host=host, port=5000)
