"""
VIKI API Server
Provides RESTful endpoints for the React dashboard
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger

app = Flask(__name__)
CORS(app)

# Initialize VIKI Controller
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
soul_path = os.path.join(base_dir, "config", "soul.yaml")
settings_path = os.path.join(base_dir, "config", "settings.yaml")

controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

@app.route('/api/health', methods=['GET'])
async def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'version': controller.soul.config.get('version', 'Unknown'),
        'name': controller.soul.config.get('name', 'VIKI')
    })

@app.route('/api/chat', methods=['POST'])
async def chat():
    """Process chat messages asynchronously"""
    data = request.json
    user_input = data.get('message', '')
    
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        # v21: Explicitly await the async controller method
        response = await controller.process_request(user_input)
        
        return jsonify({
            'response': response,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        viki_logger.error(f"API Chat Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory', methods=['GET'])
async def get_memory():
    """Retrieve conversation memory"""
    # Use get_context to fetch latest messages from DB or ephemeral memory
    messages = controller.memory.get_context()
    return jsonify({
        'messages': messages,
        'limit': controller.memory.max_short_term
    })

@app.route('/api/memory', methods=['DELETE'])
async def clear_memory():
    """Clear conversation memory"""
    if controller.memory.db:
        controller.memory.db["messages"].delete_where()
    else:
        controller.memory.ephemeral_history = []
    return jsonify({'status': 'cleared'})

@app.route('/api/skills', methods=['GET'])
async def get_skills():
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
async def get_models():
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

@app.route('/api/soul', methods=['GET'])
async def get_soul():
    """Get VIKI's persona configuration"""
    return jsonify({
        'name': controller.soul.name,
        'directives': controller.soul.directives,
        'tone': controller.soul.tone
    })

if __name__ == '__main__':
    print("Starting VIKI API Server (ASYNCHRONOUS)...")
    print(f"VIKI Version: {controller.soul.config.get('version', 'Unknown')}")
    print("API available at: http://localhost:5000")
    # Note: debug mode can sometimes interfere with async loops in some flask versions
    app.run(debug=False, host='0.0.0.0', port=5000)
