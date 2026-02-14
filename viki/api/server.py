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

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger

app = Flask(__name__)
# Explicitly allow the React/Vite dev server and production origins
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]}})

# Initialize VIKI Controller
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
soul_path = os.path.join(base_dir, "config", "soul.yaml")
settings_path = os.path.join(base_dir, "config", "settings.yaml")

controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

def async_route(f):
    """Decorator to properly handle async routes in Flask."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@app.route('/ping', methods=['GET'])
def ping():
    return "pong"

@app.route('/api/health', methods=['GET'])
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
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500

@app.route('/api/memory', methods=['GET'])
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
def clear_memory():
    """Clear conversation memory"""
    if controller.memory.working.db:
        controller.memory.working.db["messages"].delete_where()
    else:
        controller.memory.working.ephemeral_history = []
    return jsonify({'status': 'cleared'})

@app.route('/api/skills', methods=['GET'])
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

@app.route('/api/world', methods=['GET'])
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
def get_brain():
    """Get Cognitive State (Signals & Trace)"""
    return jsonify({
        'signals': controller.signals.get_modulation(),
        'trace': controller.internal_trace[-5:] if controller.internal_trace else [],
        'last_thought': controller.memory.working.get_last_thought() if hasattr(controller.memory.working, 'get_last_thought') else "",
        'mode': controller.interaction_pace
    })

@app.route('/api/missions', methods=['GET'])
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
    # Note: debug mode can sometimes interfere with async loops in some flask versions
    app.run(debug=True, host='0.0.0.0', port=5000)
