import os
import subprocess
import yaml
import json

def run_command(cmd_list):
    print(f"RUNNING: {' '.join(cmd_list)}")
    result = subprocess.run(cmd_list, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return False
    return True

def main():
    print("--- VIKI OLLAMA OVEN v1.0 ---")
    
    # 1. Export Data
    print("Extracting current wisdom...")
    # Run export script from root
    export_script = os.path.join("scripts", "export_viki_knowledge.py")
    knowledge_json = os.path.join("data", "lessons_semantic.json")
    knowledge_txt = os.path.join("data", "wisdom.txt")
    
    if not run_command(["python", export_script, "--json", knowledge_json, "--output", knowledge_txt]):
        return

    # 2. Read Knowledge
    knowledge_lines = []
    if os.path.exists(knowledge_txt):
        with open(knowledge_txt, "r", encoding="utf-8") as f:
            knowledge_lines = [line.strip() for line in f.readlines() if line.strip()]
    
    print(f"Integrating {len(knowledge_lines)} learned facts into the model weights (emulated via prompt)...")

    # 3. Build the Modelfile
    base_modelfile = os.path.join("viki", "Modelfile")
    target_modelfile = os.path.join("viki", "Modelfile.custom")
    
    with open(base_modelfile, "r", encoding="utf-8") as f:
        content = f.read()

    # Inject into the SYSTEM block if it exists
    wisdom_block = "\n# LONG-TERM MEMORY (WISDOM)\n"
    for fact in knowledge_lines:
        # Clean up fact string
        clean_fact = fact.replace("FACT:", "").strip()
        wisdom_block += f"- {clean_fact}\n"
    
    if '"""' in content:
        # Inject before the last triple quote
        parts = content.rsplit('"""', 1)
        if len(parts) == 2:
            new_modelfile = parts[0] + wisdom_block + '"""' + parts[1]
        else:
             new_modelfile = content + f"\nSYSTEM \"\"\"{wisdom_block}\"\"\""
    else:
        new_modelfile = content + f"\nSYSTEM \"\"\"{wisdom_block}\"\"\""
    
    with open(target_modelfile, "w", encoding="utf-8") as f:
        f.write(new_modelfile)

    # 4. Create Ollama Model
    model_name = "viki-born-again"
    print(f"Forging new model: {model_name}...")
    if run_command(["ollama", "create", model_name, "-f", target_modelfile]):
        print(f"\nSUCCESS! Your custom model '{model_name}' is ready.")
        print("To use it, update your viki/config/models.yaml to point to this model name.")
    else:
        print("Failed to forge model. Make sure Ollama is running.")

if __name__ == "__main__":
    main()
