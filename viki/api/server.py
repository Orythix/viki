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

load_dotenv()

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger

app = Flask(__name__)
CORS(app)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response




# Initialize VIKI Controller
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
soul_path = os.path.join(base_dir, "config", "soul.yaml")
settings_path = os.path.join(base_dir, "config", "settings.yaml")

controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

# API Key Authentication
API_KEY = os.getenv('VIKI_API_KEY')
if not API_KEY:
    # Generate a random API key if not set (for development)
    API_KEY = secrets.token_urlsafe(32)
    viki_logger.warning(f"No VIKI_API_KEY set. Generated temporary key: {API_KEY}")
    viki_logger.warning("Set VIKI_API_KEY environment variable for production use.")

@app.before_request
def log_request_info():
    viki_logger.debug(f"Request: {request.method} {request.url}")
    if request.path.startswith('/api/'):
        auth = request.headers.get('Authorization', 'Missing')
        viki_logger.debug(f"Auth Header: {auth[:15]}...")

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

@app.route('/ping', methods=['GET'])
def ping():
    viki_logger.info("PING HIT")
    return "pong"

@app.route('/api/health', methods=['GET'])
@require_api_key
def health():
    try:
        return jsonify({
            'status': 'online',
            'version': controller.soul.config.get('version', 'Unknown'),
            'name': controller.soul.config.get('name', 'VIKI')
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
        user_input = data.get('message', '')
        
        if not user_input:
            return jsonify({'error': 'No message provided'}), 400
        
        viki_logger.info(f"API: Processing user input: '{user_input[:100]}'...")
        response = await controller.process_request(user_input)
        viki_logger.info("API: Response generated successfully")
        
        return jsonify({
            'response': response,
            'timestamp': datetime.now().isoformat()
        })
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
    viki_logger.info(f"API Key required for authentication. Current key: {API_KEY[:10]}...")
    # Disable debug mode in production for security
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
