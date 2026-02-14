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

from viki.core.learning import LearningModule

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
SOUL_PATH = os.path.join(BASE_DIR, "config", "soul.yaml")
MODELFILE_PATH = os.path.join(BASE_DIR, "Modelfile")

def load_soul():
    try:
        with open(SOUL_PATH, 'r') as f:
            return yaml.safe_load(f)
    except (yaml.YAMLError, IOError, FileNotFoundError) as e:
        import logging
        logger = logging.getLogger('viki.forge')
        logger.warning(f"Failed to load soul config: {e}")
        return {}

def summarize_memories(lessons: List[str]) -> str:
    """
    Selects core facts and recent heuristics for the system prompt.
    """
    if not lessons: return ""
    
    # Simple logic: Take first 5 (likely core) and last 15 (recent)
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
    
    # Use LearningModule for data
    learning = LearningModule(DATA_DIR)
    memories = learning.get_frequent_lessons(1) # Get all for now
    
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
    
    import logging
    logger = logging.getLogger('viki.forge')
    logger.info(f"[FORGE] Building evolved core: {model_name}...")
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
    import logging
    logger = logging.getLogger('viki.forge')
    logger.info("--- VIKI NEURAL FORGE 2.0 ---")
    success = build_model()
    if success:
        logger.info("--- FORGE SUCCESSFUL ---")
    else:
        logger.error("--- FORGE FAILED ---")
    return success

if __name__ == "__main__":
    main_forge()
