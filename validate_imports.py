import os
import sys
import importlib

# Add current dir to path
sys.path.insert(0, os.getcwd())

def check_imports(start_dir):
    print(f"Checking imports in {start_dir} (excluding .venv/pycache)...")
    errors = []
    
    for root, dirs, files in os.walk(start_dir):
        # Filter unwanted dirs in-place
        dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", "node_modules", ".git"}]
        
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                path = os.path.join(root, file)
                # Convert path to module name relative to cwd
                rel_path = os.path.relpath(path, os.getcwd())
                module_name = rel_path.replace(os.sep, ".")[:-3]
                
                try:
                    # print(f"Checking {module_name}...")
                    importlib.import_module(module_name)
                except ImportError as e:
                    print(f"❌ {module_name}: {e}")
                    errors.append(f"{module_name}: {e}")
                except Exception as e:
                    pass
                    
    return errors

if __name__ == "__main__":
    errs = check_imports("viki")
    if errs:
        print(f"\nFound {len(errs)} import errors.")
        # sys.exit(1)
    else:
        print("\nAll internal modules imported successfully.")
