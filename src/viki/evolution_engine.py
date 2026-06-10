import os
import yaml
import json
import asyncio
import time
import sys
from typing import List, Dict, Any

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from viki.core.knowledge_ingestion import LearningModule
from viki.config.logger import viki_logger

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
SOUL_PATH = os.path.join(BASE_DIR, "config", "soul.yaml")
MODELFILE_PATH = os.path.join(BASE_DIR, "Modelfile")

def get_personality_prompt():
    personality_path = os.path.join(BASE_DIR, "config", "core_personality.md")
    try:
        if os.path.exists(personality_path):
            with open(personality_path, 'r', encoding='utf-8') as f:
                return f.read()
    except Exception as e:
        import logging
        logger = logging.getLogger('forge')
        logger.error(f"Error loading personality prompt: {e}")
    return ""

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
    system_prompt = get_personality_prompt()
    
    # Use LearningModule for data
    learning = LearningModule(DATA_DIR)
    memories = learning.get_frequent_lessons(1) # Get all for now
    
    memory_block = ""
    if memories:
        summary = summarize_memories(memories)
        memory_block = f"\n\nCORE SEMANTIC KNOWLEDGE:\n{summary}"

    # Also include failure avoidance
    failures = learning.get_relevant_failures("", limit=10)
    failure_block = ""
    if failures:
        fail_summary = "\n".join([f"- {f}" for f in failures])
        failure_block = f"\n\nFAILURE AVOIDANCE (Lessons from past mistakes):\n{fail_summary}"

    base_model = os.environ.get("VIKI_FORGE_BASE_OLLAMA_MODEL", "gemma4:latest").strip() or "gemma4:latest" 
    
    modelfile_content = f"""
FROM {base_model}
PARAMETER temperature 0.6
PARAMETER top_p 0.9

SYSTEM \"\"\"
{system_prompt}
{memory_block}
{failure_block}
\"\"\"
"""
    
    with open(MODELFILE_PATH, 'w', encoding='utf-8') as f:
        f.write(modelfile_content)
    
    viki_logger.info(f"Forge: Modelfile generated using base '{base_model}'")
    return MODELFILE_PATH

async def build_model():
    modelfile = create_modelfile()
    model_name = "viki-evolved"
    
    import logging
    logger = logging.getLogger('forge')
    logger.info(f"[FORGE] Building evolved core: {model_name}...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "ollama", "create", model_name, "-f", modelfile,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        if proc.returncode == 0:
            viki_logger.info(f"Forge: Model '{model_name}' updated.")
            return True
        else:
            err_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            viki_logger.error(f"Forge building error: {err_text}")
            return False
    except asyncio.TimeoutError:
        viki_logger.error("Forge: ollama create timed out after 300s.")
        return False
    except Exception as e:
        viki_logger.error(f"Forge logic error: {e}")
        return False

async def main_forge():
    import logging
    logger = logging.getLogger('forge')
    logger.info("--- VIKI NEURAL FORGE 2.0 ---")
    success = await build_model()
    if success:
        logger.info("--- FORGE SUCCESSFUL ---")
    else:
        logger.error("--- FORGE FAILED ---")
    return success

if __name__ == "__main__":
    asyncio.run(main_forge())
