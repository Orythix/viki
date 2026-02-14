
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viki.core.world import WorldModel

def verify_world_engine():
    print("--- Initializing Phase 4: World Engine ---")
    
    data_dir = os.path.join("viki", "data", "test_world")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        
    world = WorldModel(data_dir)
    
    # 1. Scan the VIKI codebase itself
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"\nScanning Project Root: {root_dir}")
    world.scan_codebase(root_dir)
    
    # 2. Simulate User Interaction with a file
    target_file = "viki/core/schema.py"
    print(f"\nSetting Active Focus: {target_file}")
    world.set_active_file(target_file)
    
    # 3. Check Understanding (Should show recursive impact)
    print("\n--- DERIVING WORLD UNDERSTANDING ---")
    understanding = world.get_understanding()
    print(understanding)
    
    # Verify specific impact detection
    if "Impacted by changes to viki/core/schema.py" in understanding:
        print("\nSUCCESS: World Engine detected files importing schema.py.")
    else:
        print("\nFAILURE: Dependency mapping did not flag recursive impacts.")

if __name__ == "__main__":
    verify_world_engine()
