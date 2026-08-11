"""Unit tests for AST Knowledge Graph code indexing."""

from __future__ import annotations

from viki.core.knowledge_graph import KnowledgeGraph


def test_index_python_code_ast():
    kg = KnowledgeGraph()
    sample_code = '''
class Calculator:
    """A sample calculator class."""
    def add(self, a: int, b: int) -> int:
        return a + b

def standalone_helper(x: int) -> int:
    return x * 2
'''

    nodes = kg.index_python_code(sample_code, file_identifier="sample.py")
    node_ids = {n.id for n in nodes}

    assert "code_file:sample.py" in node_ids
    assert "class:Calculator" in node_ids
    assert "method:Calculator.add" in node_ids
    assert "function:standalone_helper" in node_ids

    subgraph = kg.get_subgraph("class:Calculator", radius=1)
    assert len(subgraph["nodes"]) >= 2
