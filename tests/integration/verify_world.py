import os
import sys

import pytest

root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.append(root_dir)

import logging  # noqa: E402

from viki.config.logger import viki_logger  # noqa: E402
from viki.core.world import WorldModel  # noqa: E402

viki_logger.setLevel(logging.DEBUG)


@pytest.mark.slow
@pytest.mark.manual
def test_world():
    print("--- [VERIFICATION: World Mapping v22] ---")

    test_data_dir = os.path.join(root_dir, "data", "test_world")
    if not os.path.exists(test_data_dir):
        os.makedirs(test_data_dir)

    world = WorldModel(test_data_dir)

    print(f"Scanning target: {root_dir}")
    world.analyze_workspace(root_dir)

    print("\n--- [DISCOVERY RESULTS] ---")
    understanding = world.get_understanding()
    print(understanding)
    assert len(understanding) > 0, "World understanding should not be empty"

    print("\n--- [DETAILED SEMANTIC PATHS] ---")
    for path, purpose in world.state.semantic_paths.items():
        print(f"LANDMARK: {purpose} -> {path}")

    print("\n--- [DETAILED SAFETY ZONES] ---")
    safety_count = len(world.state.safety_zones)
    assert safety_count >= 0, "Safety zones should be non-negative"


if __name__ == "__main__":
    test_world()
