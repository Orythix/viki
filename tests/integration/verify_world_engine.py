import os
import sys

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.world import WorldModel


@pytest.mark.slow
@pytest.mark.manual
def test_world_engine():
    print("--- Initializing Phase 4: World Engine ---")

    data_dir = os.path.join("viki", "data", "test_world")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    world = WorldModel(data_dir)

    root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    print(f"\nScanning Project Root: {root_dir}")
    world.scan_codebase(root_dir)

    target_file = "./core/schema.py"
    print(f"\nSetting Active Focus: {target_file}")
    world.set_active_file(target_file)

    print("\n--- DERIVING WORLD UNDERSTANDING ---")
    understanding = world.get_understanding()
    print(understanding)

    if "Impacted by changes to viki/core/schema.py" in understanding:
        print("\nSUCCESS: World Engine detected files importing schema.py.")
    else:
        print("\nFAILURE: Dependency mapping did not flag recursive impacts.")


if __name__ == "__main__":
    test_world_engine()
