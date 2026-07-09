"""
Budgeted context assembler.

Ranks and selects context sources (memory, world-model state, skill schemas,
knowledge graph) per request within a token budget instead of concatenating
everything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextSource:
    """A source of context with priority and cost."""

    name: str
    content: str
    priority: float = 0.5  # 0.0–1.0
    token_cost: int = 0
    category: str = "memory"  # memory, world, skill, graph, system
    metadata: dict[str, Any] = field(default_factory=dict)


class BudgetedContextAssembler:
    """
    Assembles context within a token budget by ranking sources.

    Usage:
        assembler = BudgetedContextAssembler(max_tokens=4096)
        assembler.add_source(ContextSource("memory", "...", priority=0.9, token_cost=500))
        assembler.add_source(ContextSource("world", "...", priority=0.6, token_cost=300))
        result = assembler.assemble()
    """

    def __init__(self, max_tokens: int = 4096, reserve_system_tokens: int = 512):
        self._max_tokens = max_tokens
        self._reserve = reserve_system_tokens
        self._sources: list[ContextSource] = []
        self._budget = max_tokens - reserve_system_tokens

    def add_source(self, source: ContextSource) -> None:
        self._sources.append(source)

    def add_memory_context(self, lessons: list[str], max_tokens: int = 1500) -> None:
        text = "\n".join(lessons)
        tokens = len(text) // 4
        cost = min(tokens, max_tokens)
        self.add_source(
            ContextSource(
                name="memory",
                content=text[: cost * 4],
                priority=0.8,
                token_cost=cost,
                category="memory",
            )
        )

    def add_world_context(self, world_model: Any, query: str = "") -> None:
        try:
            if hasattr(world_model, "get_context_snapshot"):
                snapshot = world_model.get_context_snapshot(query)
            elif hasattr(world_model, "get_workspace_context"):
                snapshot = world_model.get_workspace_context()
            else:
                return
            text = str(snapshot)
            tokens = len(text) // 4
            cost = min(tokens, 800)
            self.add_source(
                ContextSource(
                    name="world",
                    content=text[: cost * 4],
                    priority=0.7,
                    token_cost=cost,
                    category="world",
                )
            )
        except Exception:
            pass

    def add_skill_context(self, skills: Any, intent: str = "", max_tokens: int = 1000) -> None:
        try:
            if hasattr(skills, "get_context_description"):
                text = skills.get_context_description(mode="metadata", skip_escalation=True)
            else:
                return
            tokens = len(text) // 4
            cost = min(tokens, max_tokens)
            self.add_source(
                ContextSource(
                    name="skills",
                    content=text[: cost * 4],
                    priority=0.6,
                    token_cost=cost,
                    category="skill",
                )
            )
        except Exception:
            pass

    def add_graph_context(self, kg: Any, query_terms: list[str]) -> None:
        try:
            if hasattr(kg, "summarize_for_context"):
                text = kg.summarize_for_context(query_terms, max_nodes=15)
            else:
                return
            if text:
                tokens = len(text) // 4
                cost = min(tokens, 600)
                self.add_source(
                    ContextSource(
                        name="knowledge_graph",
                        content=text[: cost * 4],
                        priority=0.75,
                        token_cost=cost,
                        category="graph",
                    )
                )
        except Exception:
            pass

    def assemble(self) -> str:
        """Rank sources by priority and assemble within budget."""
        # Sort by priority descending
        sorted_sources = sorted(self._sources, key=lambda s: -s.priority)

        selected: list[ContextSource] = []
        used = 0

        for source in sorted_sources:
            if source.token_cost <= 0:
                continue
            if used + source.token_cost > self._budget:
                # Try to include a truncated version
                max_alloc = self._budget - used
                if max_alloc > 100:
                    truncated = source.content[: max_alloc * 4]
                    selected.append(
                        ContextSource(
                            name=source.name,
                            content=truncated,
                            priority=source.priority,
                            token_cost=max_alloc,
                            category=source.category,
                        )
                    )
                    used += max_alloc
                continue
            selected.append(source)
            used += source.token_cost

        parts: list[str] = []
        for s in selected:
            part = s.content.strip()
            if part:
                parts.append(f"[{s.name}]\n{part}")

        return "\n\n".join(parts)

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate (chars / 4)."""
        return len(text) // 4
