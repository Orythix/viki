import asyncio
import os
import sys

import pytest
import yaml

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from viki.core.memory import HierarchicalMemory


@pytest.mark.slow
@pytest.mark.manual
@pytest.mark.asyncio
async def test_hierarchy():
    root_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    settings_path = os.path.join(root_dir, "viki", "config", "settings.yaml")

    with open(settings_path) as f:
        settings = yaml.safe_load(f)

    print("--- Initializing Hierarchical Memory ---")
    memory = HierarchicalMemory(settings)

    print(
        f"Working Memory: {memory.working.db_path if hasattr(memory.working, 'db_path') else 'Active'} (Layer 1)"
    )
    print(
        f"Episodic Memory: {memory.episodic.db_path if hasattr(memory.episodic, 'db_path') else 'Active'} (Layer 2)"
    )
    print(
        f"Identity Store: {memory.identity.db_path if hasattr(memory.identity, 'db_path') else 'Active'} (Layer 4)"
    )

    print("\n--- Testing Persistence ---")
    memory.working.add_message("user", "Hello VIKI, do you remember our last session?")
    memory.working.add_message("assistant", "Yes, we were working on your memory hierarchy.")

    memory.record_interaction(
        intent="Initialize memory system",
        action="Refactor controller and memory modules",
        outcome="Hierarchical memory active and persistent.",
        confidence=0.95,
    )

    print("\n--- Context Retrieval ---")
    full_ctx = memory.get_full_context("memory system")
    print(f"Recalled Episodes: {len(full_ctx['episodic'])}")
    print(f"Working Trace Length: {len(full_ctx['working'])}")
    assert len(full_ctx["episodic"]) >= 1, "Expected at least 1 recalled episode"
    assert len(full_ctx["working"]) >= 2, "Expected at least 2 working messages"
    assert full_ctx["identity"], "Identity grounding should not be empty"
    print(f"Identity Grounding: {full_ctx['identity'][:100]}...")

    print("\nHIERARCHY VERIFIED: ALL LAYERS OPERATIONAL.")


if __name__ == "__main__":
    asyncio.run(test_hierarchy())
