"""
VIKI API Server
Provides RESTful endpoints for the React dashboard
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from viki.core.controller import VIKIController

app = Flask(__name__)
CORS(app)

# Initialize VIKI Controller
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
soul_path = os.path.join(base_dir, "config", "soul.yaml")
settings_path = os.path.join(base_dir, "config", "settings.yaml")

controller = VIKIController(settings_path=settings_path, soul_path=soul_path)

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'version': controller.soul.config.get('version', 'Unknown'),
        'name': controller.soul.config.get('name', 'VIKI')
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Process chat messages"""
    data = request.json
    user_input = data.get('message', '')
    
    if not user_input:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        response = controller.process_request(user_input)
        
        return jsonify({
            'response': response,
            'timestamp': controller.memory.short_term_memory[-1]['timestamp'] if controller.memory.short_term_memory else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory', methods=['GET'])
def get_memory():
    """Retrieve conversation memory"""
    return jsonify({
        'messages': controller.memory.short_term_memory,
        'limit': controller.memory.max_short_term
    })

@app.route('/api/memory', methods=['DELETE'])
def clear_memory():
    """Clear conversation memory"""
    controller.memory.short_term_memory = []
    return jsonify({'status': 'cleared'})

@app.route('/api/skills', methods=['GET'])
def get_skills():
    """List all registered skills"""
    skills = []
    for name, skill in controller.skill_registry.skills.items():
        skills.append({
            'name': name,
            'description': skill.description,
            'triggers': skill.triggers
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

@app.route('/api/soul', methods=['GET'])
def get_soul():
    """Get VIKI's persona configuration"""
    return jsonify({
        'name': controller.soul.name,
        'directives': controller.soul.directives,
        'tone': controller.soul.tone
    })

if __name__ == '__main__':
    print("Starting VIKI API Server...")
    print(f"VIKI Version: {controller.soul.config.get('version', 'Unknown')}")
    print("API available at: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
