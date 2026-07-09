"""
Knowledge graph over lessons — entity/relation extraction and traversal.

Builds on the ``relationships`` table in the lesson store to provide:
  - Entity extraction from lesson text (heuristic + optional LLM)
  - Relation extraction between lessons
  - Graph traversal ("what does X depend on?", "what is related to Y?")
  - Path finding between concepts
  - Subgraph summary for context assembly
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, cast

from viki.config.logger import viki_logger


@dataclass
class GraphNode:
    """A node in the knowledge graph (an entity or concept)."""

    id: str
    label: str
    lesson_id: str = ""
    node_type: str = "concept"  # concept, entity, person, technology, etc.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge between two graph nodes."""

    source_id: str
    target_id: str
    rel_type: str  # depends_on, implements, related_to, conflicts_with, etc.
    weight: float = 1.0
    lesson_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# Heuristic entity extraction patterns
_ENTITY_PATTERNS: list[tuple[str, str]] = [
    # Technology names
    (
        r"\b(Python|JavaScript|TypeScript|Rust|Go|React|Django|FastAPI|Flask|Docker|Kubernetes|SQLite|PostgreSQL|Redis|GraphQL)\b",
        "technology",
    ),
    # People mentioned with context
    (r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", "person"),
    # Acronyms (2-5 uppercase letters)
    (r"\b([A-Z]{2,5})\b", "acronym"),
]


class KnowledgeGraph:
    """
    Knowledge graph built from lesson relationships.

    Supports traversal, pathfinding, and subgraph extraction for context
    assembly.
    """

    def __init__(self, learning_module: Any | None = None):
        self._lm = learning_module
        # In-memory cache for fast traversal
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._adjacency: dict[str, list[GraphEdge]] = defaultdict(list)
        self._dirty = True

    # ---- Build / refresh ----

    def refresh(self) -> None:
        """Rebuild the in-memory graph from the lesson store."""
        self._nodes.clear()
        self._edges.clear()
        self._adjacency.clear()

        if self._lm is None:
            return

        try:
            lessons = self._lm.get_lessons(limit=10000)
            for lesson in lessons:
                lesson_id = lesson.get("id", "")
                text = lesson.get("text_representation", "") or ""
                entities = self._extract_entities(text)

                for _eid, label, etype in entities:
                    node_id = f"entity:{label.lower().replace(' ', '_')}"
                    if node_id not in self._nodes:
                        self._nodes[node_id] = GraphNode(
                            id=node_id,
                            label=label,
                            lesson_id=lesson_id,
                            node_type=etype,
                        )

                self._load_relationships(lesson_id)

            self._dirty = False
            viki_logger.info(
                "KnowledgeGraph: loaded %d nodes, %d edges", len(self._nodes), len(self._edges)
            )
        except Exception as e:
            viki_logger.debug("KnowledgeGraph refresh failed: %s", e)

    def _load_relationships(self, lesson_id: str) -> None:
        """Load relationship edges for a lesson from the database."""
        if self._lm is None:
            return
        try:
            conn = getattr(self._lm, "conn", None)
            if conn is None:
                return
            cur = conn.cursor()
            cur.execute(
                "SELECT subj, pred, obj FROM relationships WHERE lesson_id = ?",
                (lesson_id,),
            )
            for row in cur.fetchall():
                subj, pred, obj = row["subj"], row["pred"], row["obj"]
                src_id = f"entity:{subj}"
                tgt_id = f"entity:{obj}"
                if src_id not in self._nodes:
                    self._nodes[src_id] = GraphNode(id=src_id, label=subj, lesson_id=lesson_id)
                if tgt_id not in self._nodes:
                    self._nodes[tgt_id] = GraphNode(id=tgt_id, label=obj, lesson_id=lesson_id)
                edge = GraphEdge(
                    source_id=src_id,
                    target_id=tgt_id,
                    rel_type=pred,
                    lesson_id=lesson_id,
                )
                self._edges.append(edge)
                self._adjacency[src_id].append(edge)
        except Exception as e:
            viki_logger.debug("KnowledgeGraph load_relationships failed: %s", e)

    # ---- Entity extraction ----

    def _extract_entities(self, text: str) -> list[tuple[str, str, str]]:
        """Heuristic entity extraction from lesson text."""
        entities: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for pattern, etype in _ENTITY_PATTERNS:
            for match in re.finditer(pattern, text):
                label = match.group(1)
                # Normalize ID
                entity_id = label.lower().replace(" ", "_")
                if entity_id not in seen:
                    seen.add(entity_id)
                    entities.append((entity_id, label, etype))
        return entities

    # ---- Traversal ----

    def get_related(self, node_id: str, max_depth: int = 2) -> list[GraphEdge]:
        """Get all edges connected to a node, up to *max_depth* hops."""
        visited: set[str] = set()
        results: list[GraphEdge] = []
        queue: list[tuple[str, int]] = [(node_id, 0)]

        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue
            for edge in self._adjacency.get(current, []):
                if edge not in results:
                    results.append(edge)
                    neighbor = edge.target_id if edge.source_id == current else edge.source_id
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))

        return results

    def find_path(self, source_id: str, target_id: str, max_hops: int = 5) -> list[list[GraphEdge]]:
        """Find all paths between two nodes (BFS)."""
        paths: list[list[GraphEdge]] = []
        queue: list[tuple[str, list[GraphEdge], set[str]]] = [(source_id, [], {source_id})]

        while queue:
            current, path, visited = queue.pop(0)
            if current == target_id and path:
                paths.append(path)
                continue
            if len(path) >= max_hops:
                continue
            for edge in self._adjacency.get(current, []):
                neighbor = edge.target_id if edge.source_id == current else edge.source_id
                if neighbor not in visited:
                    new_visited = visited | {neighbor}
                    queue.append((neighbor, path + [edge], new_visited))

        return paths

    def get_subgraph(self, center_id: str, radius: int = 1) -> dict[str, Any]:
        """Get a subgraph centered on a node for context assembly."""
        edges = self.get_related(center_id, max_depth=radius)
        node_ids: set[str] = {center_id}
        for e in edges:
            node_ids.add(e.source_id)
            node_ids.add(e.target_id)

        return {
            "center": self._nodes.get(center_id),
            "nodes": [self._nodes[nid] for nid in node_ids if nid in self._nodes],
            "edges": edges,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a JSON-compatible dict."""
        return {
            "nodes": [
                {"id": n.id, "label": n.label, "type": n.node_type, "lesson_id": n.lesson_id}
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.rel_type,
                    "weight": e.weight,
                }
                for e in self._edges
            ],
        }

    def summarize_for_context(self, query_terms: list[str], max_nodes: int = 20) -> str:
        """Produce a human-readable summary of relevant graph context."""
        if self._dirty:
            self.refresh()

        relevant_nodes: set[str] = set()
        for term in query_terms:
            term_lower = term.lower()
            for nid, node in self._nodes.items():
                if term_lower in node.label.lower():
                    relevant_nodes.add(nid)

        if not relevant_nodes:
            return ""

        lines: list[str] = ["[Knowledge Graph Context]"]
        for nid in list(relevant_nodes)[:max_nodes]:
            node = self._nodes[nid]
            related = self.get_related(nid, max_depth=1)
            if related:
                rel_str = "; ".join(
                    f"{e.rel_type} -> {self._nodes.get(e.target_id, GraphNode(id='', label='?')).label}"
                    if e.source_id == nid
                    else f"{self._nodes.get(e.source_id, GraphNode(id='', label='?')).label} -> {e.rel_type}"
                    for e in related[:5]
                )
                lines.append(f"  {node.label}: {rel_str}")

        return "\n".join(lines)

    def extract_and_save_relationships(
        self,
        lesson_id: str,
        lesson_text: str,
        model_router: Any | None = None,
    ) -> None:
        """Extract entities and relationships from lesson text and persist them."""
        entities = self._extract_entities(lesson_text)
        if model_router is not None:
            llm_rels = self._extract_llm_relationships(lesson_text, model_router)
        else:
            llm_rels = []

        if self._lm is None or not hasattr(self._lm, "conn"):
            return

        conn = self._lm.conn
        cur = conn.cursor()

        # Store entity nodes as relationships
        for label, etype in [(ent[1], ent[2]) for ent in entities]:
            cur.execute(
                """INSERT OR IGNORE INTO relationships (lesson_id, subj, pred, obj)
                   VALUES (?, ?, ?, ?)""",
                (lesson_id, label, f"is_{etype}", label),
            )

        for rel in llm_rels:
            subj = rel.get("subject", "")
            pred = rel.get("predicate", "")
            obj = rel.get("object", "")
            if subj and pred and obj:
                cur.execute(
                    """INSERT OR IGNORE INTO relationships (lesson_id, subj, pred, obj)
                       VALUES (?, ?, ?, ?)""",
                    (lesson_id, subj, pred, obj),
                )

        conn.commit()
        self._dirty = True

    def _extract_llm_relationships(
        self,
        text: str,
        model_router: Any,
    ) -> list[dict[str, str]]:
        """Use an LLM to extract structured relationships from text."""
        import json as _json

        prompt = [
            {
                "role": "system",
                "content": (
                    "Extract subject-predicate-object triples from the text. "
                    "Reply with ONLY a JSON array of objects with keys: subject, predicate, object. "
                    'Example: [{"subject": "Python", "predicate": "is_a", "object": "programming_language"}]. '
                    "Return [] if no relationships found."
                ),
            },
            {"role": "user", "content": text},
        ]
        try:
            import asyncio

            response = asyncio.run(model_router.chat(prompt))
            start = response.index("[")
            end = response.rindex("]")
            return cast("list[dict[str, str]]", _json.loads(response[start : end + 1]))
        except Exception as e:
            viki_logger.debug("LLM relationship extraction failed: %s", e)
            return []
