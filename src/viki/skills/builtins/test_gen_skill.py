"""Test generation skill — auto-generate pytest files from source code.

Uses the LLM to analyze source files and generate matching test files
following the project's existing test patterns (flat ``tests/`` layout,
``pytest-asyncio``, ``unittest.mock``).

Commands::

    /test-gen path/to/module.py
    /test-gen path/to/module.py --overview
    /test-gen path/to/module.py --save
"""

from __future__ import annotations

import ast
import os
from typing import Any

from viki.skills.base import BaseSkill


def _parse_functions(source: str) -> list[dict[str, Any]]:
    """Extract function/class/method signatures from Python source."""
    functions: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return functions

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func: dict[str, Any] = {
                "name": node.name,
                "kind": "async"
                if any(isinstance(d, ast.AsyncFunctionDef) for d in ast.walk(node))
                else "sync",
                "args": [arg.arg for arg in node.args.args],
                "returns": ast.unparse(node.returns) if node.returns else "None",
                "decorators": [ast.unparse(d) for d in node.decorator_list],
                "docstring": ast.get_docstring(node) or "",
            }
            functions.append(func)
        elif isinstance(node, ast.AsyncFunctionDef):
            functions.append(
                {
                    "name": node.name,
                    "kind": "async",
                    "args": [arg.arg for arg in node.args.args],
                    "returns": ast.unparse(node.returns) if node.returns else "None",
                    "decorators": [ast.unparse(d) for d in node.decorator_list],
                    "docstring": ast.get_docstring(node) or "",
                }
            )
        elif isinstance(node, ast.ClassDef):
            functions.append(
                {
                    "name": node.name,
                    "kind": "class",
                    "args": [ast.unparse(b) for b in node.bases],
                    "methods": [
                        {
                            "name": n.name,
                            "kind": "async" if isinstance(n, ast.AsyncFunctionDef) else "sync",
                            "args": [arg.arg for arg in n.args.args],
                        }
                        for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ],
                    "docstring": ast.get_docstring(node) or "",
                }
            )
    return functions


def _generate_test_content(
    module_path: str,
    source: str,
    functions: list[dict[str, Any]],
    module_name: str,
) -> str:
    """Generate pytest test file content."""
    lines: list[str] = [
        f'"""Tests for {module_path}."""',
        "",
        "from __future__ import annotations",
        "",
        "from unittest.mock import AsyncMock, MagicMock, patch",
        "",
        "import pytest",
        "",
        f"from {module_name} import (",
    ]

    # Collect importable names
    imported: list[str] = []
    for f in functions:
        if f["kind"] == "class":
            imported.append(f["name"])
        else:
            imported.append(f["name"])
    for i, name in enumerate(imported):
        comma = "," if i < len(imported) - 1 else ","
        lines.append(f"    {name}{comma}")
    lines.append(")")
    lines.append("")

    # Generate test stubs
    for func in functions:
        if func["kind"] == "class":
            lines.append("")
            lines.append(f"class Test{func['name']}:")
            for method in func.get("methods", []):
                _add_test_method(lines, method, func["name"], indent=4)
        else:
            lines.append("")
            _add_test_method(lines, func, None, indent=0)

    lines.append("")
    return "\n".join(lines)


def _add_test_method(
    lines: list[str],
    func: dict[str, Any],
    class_name: str | None,
    indent: int = 0,
) -> None:
    """Add a test method for a function."""
    prefix = " " * indent
    test_name = f"test_{func['name']}"

    is_async = func.get("kind") == "async"
    marker = "@pytest.mark.asyncio\n" if is_async else ""

    lines.append(f"{prefix}{marker}{prefix}async def {test_name}({'_' if is_async else ''}):")
    lines.append(f'{prefix}    """Test {func["name"]}."""')

    if is_async or func.get("kind") == "async":
        lines.append(f"{prefix}    # TODO: implement")
        lines.append(f"{prefix}    assert True")
    else:
        lines.append(f"{prefix}    # TODO: implement")
        lines.append(f"{prefix}    assert True")


def _get_test_path(source_path: str, tests_dir: str = "tests") -> str:
    """Determine the test file path for a given source file."""
    basename = os.path.basename(source_path)
    test_basename = f"test_{basename}"
    return os.path.join(tests_dir, test_basename)


class TestGenSkill(BaseSkill):
    """Generate pytest test stubs from Python source files."""

    @property
    def name(self) -> str:
        return "test_gen"

    @property
    def description(self) -> str:
        return (
            "Generate pytest test files for a Python module. "
            "Analyzes source code structure and creates matching test stubs. "
            "Action: test_gen(path='src/viki/core/foo.py') or test_gen(path='...', save=True)."
        )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the Python source file to generate tests for.",
                },
                "save": {
                    "type": "boolean",
                    "description": "If true, write the generated test file to disk.",
                    "default": False,
                },
                "overview": {
                    "type": "boolean",
                    "description": "If true, just list the functions/classes found without generating tests.",
                    "default": False,
                },
                "tests_dir": {
                    "type": "string",
                    "description": "Directory to write test files (default: 'tests').",
                    "default": "tests",
                },
            },
            "required": ["path"],
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    async def execute(self, params: dict[str, Any]) -> str:
        source_path = (params.get("path") or "").strip()
        if not source_path:
            return "Error: 'path' parameter is required."

        if not os.path.isfile(source_path):
            return f"Error: file not found: {source_path}"

        if not source_path.endswith(".py"):
            return "Error: only Python (.py) files are supported."

        try:
            with open(source_path, encoding="utf-8") as fh:
                source = fh.read()
        except Exception as e:
            return f"Error reading {source_path}: {e}"

        functions = _parse_functions(source)
        if not functions:
            return f"No functions or classes found in {source_path}."

        # Module name for imports
        rel_path = os.path.relpath(source_path).replace(os.sep, "/").replace("/", ".")
        module_name = rel_path.replace(".py", "")

        if params.get("overview"):
            lines = [f"Functions/classes in {source_path}:", ""]
            for func in functions:
                if func["kind"] == "class":
                    bases = f"({', '.join(func.get('args', []))})" if func.get("args") else ""
                    lines.append(f"  class {func['name']}{bases}")
                    for m in func.get("methods", []):
                        lines.append(
                            f"    {'async ' if m['kind'] == 'async' else ''}def {m['name']}({', '.join(m['args'])})"
                        )
                else:
                    lines.append(
                        f"  {'async ' if func['kind'] == 'async' else ''}def {func['name']}({', '.join(func.get('args', []))})"
                    )
            lines.append("")
            lines.append(f"Total: {len(functions)} definitions.")
            return "\n".join(lines)

        content = _generate_test_content(source_path, source, functions, module_name)
        test_path = _get_test_path(source_path, tests_dir=params.get("tests_dir", "tests"))

        if params.get("save"):
            try:
                os.makedirs(os.path.dirname(test_path) or ".", exist_ok=True)
                with open(test_path, "w", encoding="utf-8") as fh:
                    fh.write(content)
                return f"Test file saved to {test_path}\n\n{content}"
            except Exception as e:
                return f"Error writing {test_path}: {e}\n\nGenerated content:\n{content}"

        return f"Generated test for {source_path} ({len(functions)} definitions):\n\n{content}"
