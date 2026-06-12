"""Dev tool providers — blocking I/O offloaded to thread pool."""

from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoProfile:
    languages: list[str]
    frameworks: list[str]
    build_system: str | None
    test_framework: str | None
    has_docker: bool
    has_ci: bool
    entry_points: list[str]
    config_files: list[str]


class DevProvider:
    """Development analysis provider."""

    def __init__(self):
        self._language_extensions = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".jsx": "React",
            ".tsx": "React TypeScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cs": "C#",
            ".cpp": "C++",
            ".c": "C",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".scala": "Scala",
            ".r": "R",
            ".sh": "Shell",
            ".sql": "SQL",
        }

    async def analyze_repository(self, path: str) -> RepoProfile:
        root = Path(path)

        def _scan():
            languages = set()
            frameworks = set()
            config_files = []
            entry_points = []

            for file_path in root.rglob("*"):
                if file_path.is_file():
                    ext = file_path.suffix.lower()
                    if ext in self._language_extensions:
                        languages.add(self._language_extensions[ext])

                    name = file_path.name.lower()
                    if name in (
                        "pyproject.toml",
                        "setup.py",
                        "requirements.txt",
                        "package.json",
                        "tsconfig.json",
                        "cargo.toml",
                        "go.mod",
                        "pom.xml",
                        "build.gradle",
                        "composer.json",
                        "dockerfile",
                        "docker-compose.yml",
                        ".github/workflows",
                        ".gitlab-ci.yml",
                        "jenkinsfile",
                        "Makefile",
                    ):
                        config_files.append(str(file_path.relative_to(root)))

                    if name in (
                        "main.py",
                        "app.py",
                        "index.js",
                        "index.ts",
                        "main.go",
                        "main.rs",
                        "Program.cs",
                    ):
                        entry_points.append(str(file_path.relative_to(root)))

            return languages, frameworks, config_files, entry_points

        languages, frameworks, config_files, entry_points = await asyncio.to_thread(_scan)

        # Detect frameworks from config
        for config in config_files:
            if "package.json" in config:
                frameworks.update(await self._detect_js_frameworks(root / config))
            elif "pyproject.toml" in config or "requirements.txt" in config:
                frameworks.update(await self._detect_py_frameworks(root / config))

        has_docker = any("docker" in c.lower() for c in config_files)
        has_ci = any(
            c in config_files for c in (".github/workflows", ".gitlab-ci.yml", "jenkinsfile")
        )

        # Build system (fast path checks via async exists)
        build_system = None

        async def _check_build():
            b = None
            if await asyncio.to_thread((root / "pyproject.toml").exists):
                b = "pip/poetry"
            elif await asyncio.to_thread((root / "package.json").exists):
                b = "npm/yarn/pnpm"
            elif await asyncio.to_thread((root / "cargo.toml").exists):
                b = "cargo"
            elif await asyncio.to_thread((root / "go.mod").exists):
                b = "go modules"
            elif await asyncio.to_thread((root / "pom.xml").exists):
                b = "maven"
            elif await asyncio.to_thread((root / "build.gradle").exists):
                b = "gradle"
            return b

        build_system = await _check_build()

        # Test framework
        async def _check_test():
            t = None
            if await asyncio.to_thread((root / "pytest.ini").exists) or await asyncio.to_thread(
                (root / "pyproject.toml").exists
            ):
                t = "pytest"
            elif await asyncio.to_thread(
                (root / "jest.config.js").exists
            ) or await asyncio.to_thread((root / "vitest.config.ts").exists):
                t = "jest/vitest"
            elif await asyncio.to_thread((root / "cargo.toml").exists):
                t = "cargo test"
            return t

        test_framework = await _check_test()

        return RepoProfile(
            languages=sorted(languages),
            frameworks=sorted(frameworks),
            build_system=build_system,
            test_framework=test_framework,
            has_docker=has_docker,
            has_ci=has_ci,
            entry_points=entry_points,
            config_files=config_files,
        )

    async def _detect_js_frameworks(self, package_json: Path) -> set[str]:
        frameworks = set()

        def _():
            try:
                data = json.loads(package_json.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "react" in deps:
                    frameworks.add("React")
                if "vue" in deps:
                    frameworks.add("Vue")
                if "angular" in deps or "@angular/core" in deps:
                    frameworks.add("Angular")
                if "next" in deps:
                    frameworks.add("Next.js")
                if "express" in deps:
                    frameworks.add("Express")
                if "fastify" in deps:
                    frameworks.add("Fastify")
                if "svelte" in deps:
                    frameworks.add("Svelte")
            except Exception:
                pass

        await asyncio.to_thread(_)
        return frameworks

    async def _detect_py_frameworks(self, config_file: Path) -> set[str]:
        frameworks = set()

        def _():
            try:
                content = config_file.read_text().lower()
                if "fastapi" in content:
                    frameworks.add("FastAPI")
                if "django" in content:
                    frameworks.add("Django")
                if "flask" in content:
                    frameworks.add("Flask")
                if "starlette" in content:
                    frameworks.add("Starlette")
                if "sqlalchemy" in content:
                    frameworks.add("SQLAlchemy")
                if "pydantic" in content:
                    frameworks.add("Pydantic")
            except Exception:
                pass

        await asyncio.to_thread(_)
        return frameworks

    async def analyze_python_file(self, path: str) -> dict:
        """Analyze a Python file for functions, classes, imports."""
        file_path = Path(path)

        def _():
            if not file_path.exists():
                return {"error": "File not found"}
            content = file_path.read_text()
            tree = ast.parse(content)

            functions = []
            classes = []
            imports = []

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(
                        {
                            "name": node.name,
                            "args": [a.arg for a in node.args.args],
                            "line": node.lineno,
                            "docstring": ast.get_docstring(node),
                        }
                    )
                elif isinstance(node, ast.ClassDef):
                    classes.append(
                        {
                            "name": node.name,
                            "methods": [
                                n.name for n in node.body if isinstance(n, ast.FunctionDef)
                            ],
                            "line": node.lineno,
                            "docstring": ast.get_docstring(node),
                        }
                    )
                elif isinstance(node, ast.Import | ast.ImportFrom):
                    for alias in node.names:
                        imports.append(
                            {
                                "module": node.module
                                if isinstance(node, ast.ImportFrom)
                                else alias.name,
                                "name": alias.name,
                                "alias": alias.asname,
                            }
                        )

            return {
                "file": str(file_path),
                "functions": functions,
                "classes": classes,
                "imports": imports,
            }

        return await asyncio.to_thread(_)
