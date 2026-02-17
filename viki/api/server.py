"""
VIKI API Server
Provides RESTful endpoints for the React dashboard
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import sys
import os
import asyncio
from functools import wraps
import secrets
from dotenv import load_dotenv
import threading
import time

load_dotenv()

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController
from viki.core.safety import safe_for_log
from viki.config.logger import viki_logger
from viki.config.resolve import get_soul_path

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
settings_path = os.path.join(base_dir, "config", "settings.yaml")
soul_path = get_soul_path(settings_path)

controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

app = Flask(__name__)

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
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
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
    viki_logger.debug(f"Request: {request.method} {request.url}")
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
        tools = list(controller.skill_registry.skills.keys()) if hasattr(controller, 'skill_registry') and controller.skill_registry else []
        return jsonify({
            'status': 'online',
            'version': controller.soul.config.get('version', 'Unknown'),
            'name': controller.soul.config.get('name', 'VIKI'),
            'persona': getattr(controller, 'persona', 'sovereign'),
            'tagline': controller.soul.config.get('tagline') or controller.soul.config.get('positioning', ''),
            'differentiators': controller.get_differentiators(),
            'tools': tools,
        })
    except Exception as e:
        viki_logger.error(f"Health check error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
@require_api_key
@async_route
async def chat():
    """Process chat messages asynchronously"""
    try:
        viki_logger.info("API: Chat request received")
        data = request.json
        
        if not data:
            return jsonify({'error': 'Invalid JSON body'}), 400
        
        user_input = data.get('message', '')

        # --- SECURITY FIX: MED-003 - Input validation ---
        is_valid, error_msg = validate_message(user_input)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        viki_logger.info(f"API: Processing user input: '{safe_for_log(user_input)}'...")
        timeout_sec = controller.settings.get('system', {}).get('request_timeout_seconds', 0)
        if timeout_sec <= 0:
            timeout_sec = 600  # Ceiling when disabled so one stuck request does not hold worker indefinitely
        try:
            response = await asyncio.wait_for(controller.process_request(user_input), timeout=float(timeout_sec))
        except asyncio.TimeoutError:
            viki_logger.warning(f"API: Request timed out after {timeout_sec}s")
            return jsonify({'error': 'Request timed out. Try a shorter or simpler request.'}), 504
        viki_logger.info("API: Response generated successfully")
        
        payload = {
            'response': response,
            'timestamp': datetime.now().isoformat()
        }
        meta = getattr(controller, '_last_response_meta', None)
        if meta:
            payload['subtasks'] = meta.get('subtasks')
            payload['total_steps'] = meta.get('total_steps')
        return jsonify(payload)
    except Exception as e:
        viki_logger.error(f"API chat error: {e}", exc_info=True)
        # Don't expose internal error details to client
        return jsonify({'error': "An internal error occurred while processing your request."}), 500

@app.route('/api/memory', methods=['GET'])
@require_api_key
def get_memory():
    """Retrieve conversation memory"""
    try:
        # Use get_context to fetch latest messages from DB or ephemeral memory
        messages = controller.memory.working.get_trace()
        return jsonify({
            'messages': messages,
            'limit': controller.memory.working.max_turns
        })
    except Exception as e:
        viki_logger.error(f"Memory retrieval error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory', methods=['DELETE'])
@require_api_key
def clear_memory():
    """Clear conversation memory"""
    if controller.memory.working.db:
        controller.memory.working.db["messages"].delete_where()
    else:
        controller.memory.working.ephemeral_history = []
    return jsonify({'status': 'cleared'})

@app.route('/api/skills', methods=['GET'])
@require_api_key
def get_skills():
    """List all registered skills"""
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
                    'provider': model.config.get('provider', 'unknown'),
                    'capabilities': model.config.get('capabilities', []),
                    'priority': model.config.get('priority', 2),
                    'trust_score': round(model.trust_score, 3),
                    'avg_latency': round(model.avg_latency, 3),
                    'call_count': model.call_count,
                    'error_count': model.error_count,
                    'error_rate': round(error_rate, 3),
                    'strengths': model.strengths,
                    'weaknesses': model.weaknesses
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

@app.route('/api/world', methods=['GET'])
@require_api_key
def get_world():
    """Get World Engine state (Phase 4)"""
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
    return jsonify({
        'signals': controller.signals.get_modulation(),
        'trace': controller.internal_trace[-5:] if controller.internal_trace else [],
        'last_thought': controller.memory.working.get_last_thought() if hasattr(controller.memory.working, 'get_last_thought') else "",
        'mode': controller.interaction_pace
    })

@app.route('/api/missions', methods=['GET'])
@require_api_key
def get_missions():
    """Get Active Autonomous Missions (Phase 6)"""
    missions = []
    if hasattr(controller, 'mission_control'):
        # Convert heap to list for display
        queue = [m.to_dict() for m in controller.mission_control.mission_queue]
        # Dict to list
        active = [m.to_dict() for m in controller.mission_control.active_missions.values()]
        return jsonify({'queue': queue, 'active': active})
    return jsonify({'queue': [], 'active': []})

if __name__ == '__main__':
    viki_logger.info("Starting VIKI API Server (ASYNCHRONOUS)...")
    viki_logger.info(f"VIKI Version: {controller.soul.config.get('version', 'Unknown')}")
    viki_logger.info("API available at: http://localhost:5000")
    # SECURITY: Don't log any part of the API key
    viki_logger.info("API Key required for authentication. Key configured: Yes")
    # Disable debug mode in production for security
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    # SECURITY FIX: CRIT-001 - Bind to localhost only, not all interfaces
    # Use 127.0.0.1 instead of 0.0.0.0 to prevent network exposure
    app.run(debug=debug_mode, host='127.0.0.1', port=5000)
