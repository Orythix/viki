"""
Budgeted context assembler.

Ranks and selects context sources (memory, world-model state, skill schemas,
knowledge graph) per request within a *token-true* budget. Reserved slices keep
plan + tool schemas at the edges (lost-in-the-middle mitigation); memory/world
are compressed first via query-conditioned extractive keep.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from viki.core.utils.token_optimizer import count_tokens, extractive_keep, truncate_to_tokens


@dataclass
class ContextSource:
    """A source of context with priority and cost."""

    name: str
    content: str
    priority: float = 0.5  # 0.0–1.0
    token_cost: int = 0
    category: str = "memory"  # memory, world, skill, graph, system, plan
    metadata: dict[str, Any] = field(default_factory=dict)


# Default reserved budget fractions of the *usable* (non-system) budget.
_DEFAULT_SLICES: dict[str, float] = {
    "skill": 0.22,  # tool schemas — kept near edges
    "plan": 0.18,  # current plan — kept near edges
    "memory": 0.35,
    "world": 0.15,
    "graph": 0.10,
}


class BudgetedContextAssembler:
    """
    Assembles context within a token budget by ranking sources.

    Usage:
        assembler = BudgetedContextAssembler(max_tokens=4096)
        assembler.add_source(ContextSource("memory", "...", priority=0.9, token_cost=500))
        assembler.add_source(ContextSource("world", "...", priority=0.6, token_cost=300))
        result = assembler.assemble()
    """

    def __init__(
        self,
        max_tokens: int = 4096,
        reserve_system_tokens: int = 512,
        slices: dict[str, float] | None = None,
        query: str = "",
    ):
        self._max_tokens = max_tokens
        self._reserve = reserve_system_tokens
        self._sources: list[ContextSource] = []
        self._budget = max(0, max_tokens - reserve_system_tokens)
        self._slices = dict(_DEFAULT_SLICES)
        if slices:
            self._slices.update(slices)
        self._query = query
        self._plan_text: str = ""
        self._last_assembly_stats: dict[str, Any] = {}

    def set_query(self, query: str) -> None:
        self._query = query or ""

    def set_plan(self, plan: str) -> None:
        """Current plan text — reserved edge slice, never mid-packed alone."""
        self._plan_text = plan or ""

    def add_source(self, source: ContextSource) -> None:
        if source.token_cost <= 0 and source.content:
            source.token_cost = count_tokens(source.content)
        self._sources.append(source)

    def _slice_budget(self, category: str) -> int:
        frac = self._slices.get(category, 0.1)
        return max(0, int(self._budget * frac))

    def add_memory_context(self, lessons: list[str], max_tokens: int | None = None) -> None:
        text = "\n".join(lessons)
        budget = max_tokens if max_tokens is not None else self._slice_budget("memory")
        compressed = extractive_keep(text, self._query, budget, preserve_citations=True)
        if not compressed:
            compressed = truncate_to_tokens(text, budget)
        self.add_source(
            ContextSource(
                name="memory",
                content=compressed,
                priority=0.8,
                token_cost=count_tokens(compressed),
                category="memory",
            )
        )

    def add_world_context(self, world_model: Any, query: str = "") -> None:
        try:
            if hasattr(world_model, "get_context_snapshot"):
                snapshot = world_model.get_context_snapshot(query or self._query)
            elif hasattr(world_model, "get_workspace_context"):
                snapshot = world_model.get_workspace_context()
            else:
                return
            text = str(snapshot)
            budget = self._slice_budget("world")
            compressed = extractive_keep(
                text, query or self._query, budget, preserve_citations=True
            )
            if not compressed:
                compressed = truncate_to_tokens(text, budget)
            self.add_source(
                ContextSource(
                    name="world",
                    content=compressed,
                    priority=0.7,
                    token_cost=count_tokens(compressed),
                    category="world",
                )
            )
        except Exception:
            pass

    def add_skill_context(self, skills: Any, intent: str = "", max_tokens: int | None = None) -> None:
        try:
            if hasattr(skills, "get_context_description"):
                text = skills.get_context_description(mode="metadata", skip_escalation=True)
            else:
                return
            budget = max_tokens if max_tokens is not None else self._slice_budget("skill")
            content = truncate_to_tokens(text, budget)
            self.add_source(
                ContextSource(
                    name="skills",
                    content=content,
                    priority=0.95,  # high — tools sit at edges
                    token_cost=count_tokens(content),
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
                budget = self._slice_budget("graph")
                content = truncate_to_tokens(text, budget)
                self.add_source(
                    ContextSource(
                        name="knowledge_graph",
                        content=content,
                        priority=0.75,
                        token_cost=count_tokens(content),
                        category="graph",
                    )
                )
        except Exception:
            pass

    def assemble(self) -> str:
        """
        Assemble within budget.

        Layout (lost-in-the-middle mitigation):
          [skills] → [plan] → [memory/world/graph by priority] → [plan reprise] → [skills reprise]
        Soft sources compress first when over budget.
        """
        sources = list(self._sources)
        if self._plan_text:
            plan_budget = self._slice_budget("plan")
            plan_content = truncate_to_tokens(self._plan_text, plan_budget)
            sources.append(
                ContextSource(
                    name="plan",
                    content=plan_content,
                    priority=0.99,
                    token_cost=count_tokens(plan_content),
                    category="plan",
                )
            )

        # Compress soft categories first if over budget.
        total = sum(s.token_cost for s in sources)
        if total > self._budget:
            soft = [s for s in sources if s.category in ("memory", "world", "graph")]
            hard = [s for s in sources if s.category not in ("memory", "world", "graph")]
            soft_budget = max(0, self._budget - sum(s.token_cost for s in hard))
            soft.sort(key=lambda s: -s.priority)
            kept_soft: list[ContextSource] = []
            used_soft = 0
            for s in soft:
                if used_soft + s.token_cost <= soft_budget:
                    kept_soft.append(s)
                    used_soft += s.token_cost
                else:
                    remain = soft_budget - used_soft
                    if remain > 32:
                        trimmed = truncate_to_tokens(s.content, remain)
                        kept_soft.append(
                            ContextSource(
                                name=s.name,
                                content=trimmed,
                                priority=s.priority,
                                token_cost=count_tokens(trimmed),
                                category=s.category,
                            )
                        )
                        used_soft += count_tokens(trimmed)
            sources = hard + kept_soft

        by_cat: dict[str, list[ContextSource]] = {}
        for s in sources:
            by_cat.setdefault(s.category, []).append(s)

        def _join(cat: str) -> str:
            parts = []
            for s in by_cat.get(cat, []):
                part = s.content.strip()
                if part:
                    parts.append(f"[{s.name}]\n{part}")
            return "\n\n".join(parts)

        skills = _join("skill")
        plan = _join("plan")
        middle_cats = ("memory", "world", "graph", "system")
        middle_parts: list[str] = []
        middle_sources = []
        for cat in middle_cats:
            middle_sources.extend(by_cat.get(cat, []))
        middle_sources.sort(key=lambda s: -s.priority)
        for s in middle_sources:
            part = s.content.strip()
            if part:
                middle_parts.append(f"[{s.name}]\n{part}")
        middle = "\n\n".join(middle_parts)

        # Edges: skills + plan at start and end; soft content in the middle.
        blocks: list[str] = []
        if skills:
            blocks.append(skills)
        if plan:
            blocks.append(plan)
        if middle:
            blocks.append(middle)
        if plan:
            blocks.append(f"[plan_reprise]\n{plan}")
        if skills:
            blocks.append(f"[skills_reprise]\n{skills}")

        assembled = "\n\n".join(blocks)
        used = count_tokens(assembled)
        if used > self._budget:
            assembled = truncate_to_tokens(assembled, self._budget)
            used = count_tokens(assembled)

        self._last_assembly_stats = {
            "max_tokens": self._max_tokens,
            "reserve_system_tokens": self._reserve,
            "usable_budget": self._budget,
            "used_tokens": used,
            "slices": dict(self._slices),
            "categories": {c: sum(x.token_cost for x in xs) for c, xs in by_cat.items()},
        }
        return assembled

    def estimate_tokens(self, text: str) -> int:
        """Token-true estimate."""
        return count_tokens(text)

    def assembly_stats(self) -> dict[str, Any]:
        return dict(self._last_assembly_stats)

    async def assemble_parallel_sources(
        self,
        lessons: list[str] | None = None,
        world_model: Any | None = None,
        kg: Any | None = None,
        query: str = "",
    ) -> str:
        """Populates context sources in parallel via asyncio.gather and assembles prompt context."""
        import asyncio

        if query:
            self.set_query(query)

        tasks = []
        if lessons:
            tasks.append(asyncio.to_thread(self.add_memory_context, lessons))
        if world_model:
            tasks.append(asyncio.to_thread(self.add_world_context, world_model, query))
        if kg:
            query_terms = query.split() if query else []
            tasks.append(asyncio.to_thread(self.add_graph_context, kg, query_terms))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return self.assemble()
