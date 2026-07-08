import os

# Add project root to sys.path for imports
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import logging  # noqa: E402

from viki.config.logger import viki_logger  # noqa: E402
from viki.core.world import WorldModel  # noqa: E402

# Set logger to DEBUG to see the discovery traces
viki_logger.setLevel(logging.DEBUG)


def verify():
    print("--- [VERIFICATION: World Mapping v22] ---")

    # Initialize WorldModel in a test data location
    test_data_dir = os.path.join(root_dir, "data", "test_world")
    if not os.path.exists(test_data_dir):
        os.makedirs(test_data_dir)

    world = WorldModel(test_data_dir)

    # Target the main project directory for mapping (since it has the best markers)
    print(f"Scanning target: {root_dir}")
    world.analyze_workspace(root_dir)

    print("\n--- [DISCOVERY RESULTS] ---")
    understanding = world.get_understanding()
    print(understanding)

    print("\n--- [DETAILED SEMANTIC PATHS] ---")
    for path, purpose in world.state.semantic_paths.items():
        print(f"LANDMARK: {purpose} -> {path}")

    print("\n--- [DETAILED SAFETY ZONES] ---")
    for path, zone in world.state.safety_zones.items():
        print(f"ZONE: {zone} -> {path}")

    print("\nVerification Complete.")


if __name__ == "__main__":
    verify()
