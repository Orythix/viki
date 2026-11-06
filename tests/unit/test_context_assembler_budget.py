"""Token-true context assembler reserved slices."""

from __future__ import annotations

from viki.core.context_assembler import BudgetedContextAssembler, ContextSource
from viki.core.utils.token_optimizer import count_tokens


def test_reserved_slices_put_plan_and_skills_at_edges():
    asm = BudgetedContextAssembler(max_tokens=800, reserve_system_tokens=100, query="auth bug")
    asm.set_plan("1. reproduce\n2. fix auth middleware\n3. add regression test")
    asm.add_source(
        ContextSource(
            name="skills",
            content="tool schema: shell, filesystem, plan_edit " * 20,
            priority=0.9,
            category="skill",
        )
    )
    asm.add_memory_context(
        ["lesson: prefer oauth refresh", "cite: https://example.com/auth", "noise " * 200]
    )
    asm.add_source(
        ContextSource(
            name="world",
            content="cwd=/repo path=src/auth.py " * 40,
            priority=0.6,
            category="world",
        )
    )
    out = asm.assemble()
    stats = asm.assembly_stats()
    assert stats["used_tokens"] <= stats["usable_budget"]
    assert "[skills]" in out
    assert "[plan]" in out
    # Edge placement: skills appear before middle memory/world content
    first_skill = out.find("[skills]")
    mid = out.find("[memory]")
    if mid == -1:
        mid = out.find("[world]")
    assert first_skill != -1
    if mid != -1:
        assert first_skill < mid


def test_count_tokens_nonempty():
    assert count_tokens("hello world") >= 1
    assert count_tokens("") == 0
