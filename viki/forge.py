import os
import yaml
import json
import subprocess
import time
import sys
from typing import List, Dict, Any

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from viki.config.logger import viki_logger

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOUL_PATH = os.path.join(BASE_DIR, "config", "soul.yaml")
MEMORY_PATH = os.path.join(BASE_DIR, "..", "data", "lessons_semantic.json")
MODELFILE_PATH = os.path.join(BASE_DIR, "Modelfile")

def load_soul():
    try:
        with open(SOUL_PATH, 'r') as f:
            return yaml.safe_load(f)
    except:
        return {}

def load_memory_data():
    if os.path.exists(MEMORY_PATH):
        try:
            with open(MEMORY_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def prune_memories(data: Dict[str, Any], days=30):
    """
    Remove memories that haven't been accessed for certain days.
    """
    if not data or 'lessons' not in data: return data
    
    now = time.time()
    max_age = days * 24 * 60 * 60
    
    lessons = data.get('lessons', [])
    metadata = data.get('metadata', [])
    embeddings = data.get('embeddings', [])
    
    # If no metadata, we can't prune accurately, assume all are fresh
    if not metadata: return data
    
    indices_to_keep = []
    for i, meta in enumerate(metadata):
        if now - meta.get('last_accessed', 0) < max_age:
            indices_to_keep.append(i)
            
    if len(indices_to_keep) == len(lessons):
        return data
        
    print(f"[FORGE] Pruning {len(lessons) - len(indices_to_keep)} stale memories...")
    
    data['lessons'] = [lessons[i] for i in indices_to_keep]
    data['metadata'] = [metadata[i] for i in indices_to_keep]
    data['embeddings'] = [embeddings[i] for i in indices_to_keep]
    
    with open(MEMORY_PATH, 'w') as f:
        json.dump(data, f)
        
    return data

def summarize_memories(lessons: List[str]) -> str:
    """
    In a high-resource environment, we would use an LLM here.
    For the stable forge, we select high-frequency facts and recent heuristics.
    """
    if not lessons: return ""
    
    # Simple logic: Take most recent 15 and 5 oldest (core identity)
    if len(lessons) <= 20:
        return "\n".join([f"- {m}" for m in lessons])
        
    core = lessons[:5]
    recent = lessons[-15:]
    
    summary = "\n".join([f"- {m}" for m in core])
    summary += "\n...\n"
    summary += "\n".join([f"- {m}" for m in recent])
    
    return summary

def create_modelfile():
    viki_logger.info("Forge: Initiating Modelfile generation...")
    soul = load_soul()
    system_prompt = soul.get('system_prompt', '')
    
    memory_data = load_memory_data()
    # Prune before baking
    memory_data = prune_memories(memory_data)
    
    memories = memory_data.get('lessons', [])
    memory_block = ""
    if memories:
        summary = summarize_memories(memories)
        memory_block = f"\n\nCORE SEMANTIC KNOWLEDGE:\n{summary}"

    base_model = "phi3" 
    
    modelfile_content = f"""
FROM {base_model}
PARAMETER temperature 0.6
PARAMETER top_p 0.9

SYSTEM \"\"\"
{system_prompt}
{memory_block}
\"\"\"
"""
    
    with open(MODELFILE_PATH, 'w') as f:
        f.write(modelfile_content)
    
    viki_logger.info(f"Forge: Modelfile generated using base '{base_model}'")
    return MODELFILE_PATH

def build_model():
    modelfile = create_modelfile()
    model_name = "viki-evolved"
    
    print(f"[FORGE] Building evolved core: {model_name}...")
    try:
        result = subprocess.run(["ollama", "create", model_name, "-f", modelfile], capture_output=True, text=True)
        if result.returncode == 0:
            viki_logger.info(f"Forge: Model '{model_name}' updated.")
            return True
        else:
            viki_logger.error(f"Forge building error: {result.stderr}")
            return False
    except Exception as e:
        viki_logger.error(f"Forge logic error: {e}")
        return False

def main_forge():
    print("--- VIKI NEURAL FORGE 2.0 ---")
    success = build_model()
    if success:
        print("--- FORGE SUCCESSFUL ---")
    else:
        print("--- FORGE FAILED ---")
    return success

if __name__ == "__main__":
    main_forge()
