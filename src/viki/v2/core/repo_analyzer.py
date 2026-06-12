"""RepoAnalyzer — automatically detects project stack, languages, frameworks, and conventions."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field


@dataclass
class RepositoryProfile:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    build_system: str = ""
    test_framework: str = ""
    has_docker: bool = False
    has_ci_cd: bool = False
    has_database: bool = False
    database_type: str | None = None
    cloud_provider: str | None = None
    architecture_pattern: str = "monolith"
    package_manager: str = ""


_FILE_SIGNATURES: dict[str, tuple[list[str], list[str], str, str]] = {
    "package.json": (["JavaScript", "TypeScript"], [], "npm", "jest"),
    "yarn.lock": (["JavaScript", "TypeScript"], [], "yarn", "jest"),
    "pnpm-lock.yaml": (["JavaScript", "TypeScript"], [], "pnpm", "jest"),
    "pyproject.toml": (["Python"], [], "pip", "pytest"),
    "poetry.lock": (["Python"], [], "poetry", "pytest"),
    "requirements.txt": (["Python"], [], "pip", "pytest"),
    "Cargo.toml": (["Rust"], [], "cargo", "cargo-test"),
    "go.mod": (["Go"], [], "go", "go-test"),
    "Gemfile": (["Ruby"], [], "bundler", "rspec"),
    "pom.xml": (["Java"], [], "maven", "junit"),
    "build.gradle": (["Java", "Kotlin"], [], "gradle", "junit"),
    "CMakeLists.txt": (["C", "C++"], [], "cmake", ""),
    "Dockerfile": ([], [], "", ""),
    "docker-compose.yml": ([], [], "", ""),
    "docker-compose.yaml": ([], [], "", ""),
    ".github/workflows": ([], [], "", ""),
    ".gitlab-ci.yml": ([], [], "", ""),
    "Jenkinsfile": ([], [], "", ""),
    "tsconfig.json": ([], ["TypeScript"], "", ""),
    "next.config.js": ([], ["Next.js"], "", ""),
    "next.config.ts": ([], ["Next.js"], "", ""),
    "vite.config.ts": ([], ["Vite"], "", ""),
    "vite.config.js": ([], ["Vite"], "", ""),
    "angular.json": ([], ["Angular"], "", ""),
    "nuxt.config.ts": ([], ["Nuxt"], "", ""),
    "nuxt.config.js": ([], ["Nuxt"], "", ""),
}

_FRAMEWORK_PATTERNS: list[tuple[str, str]] = [
    ("fastapi", "FastAPI"),
    ("flask", "Flask"),
    ("django", "Django"),
    ("react", "React"),
    ("vue", "Vue"),
    ("svelte", "Svelte"),
    ("express", "Express"),
    ("spring", "Spring"),
    ("actix", "Actix"),
    ("rocket", "Rocket"),
    ("axum", "Axum"),
]


class RepoAnalyzer:
    """Walks a repository and detects its technology stack."""

    async def analyze(self, path: str = ".") -> RepositoryProfile:
        """Walk the repository and detect technologies in use."""

        def _walk():
            profile = RepositoryProfile()

            if not os.path.isdir(path):
                return profile

            for root, dirs, files in os.walk(path):
                dirs[:] = [
                    d
                    for d in dirs
                    if not d.startswith(
                        (".", "node_modules", "venv", "__pycache__", "build", "dist")
                    )
                ]

                for file in files:
                    self._classify_file(file, root, profile)

                for dirname in dirs:
                    rel = os.path.relpath(os.path.join(root, dirname), path)
                    if rel in _FILE_SIGNATURES:
                        self._classify_file(dirname, root, profile)

            self._deduplicate(profile)
            self._detect_cloud(profile)
            self._detect_architecture(profile)
            return profile

        return await asyncio.to_thread(_walk)

    def _classify_file(self, file: str, root: str, profile: RepositoryProfile):
        sig = _FILE_SIGNATURES.get(file)
        if sig:
            langs, frameworks, build_sys, test_fw = sig
            if file == "Dockerfile":
                profile.has_docker = True
            elif file in ("docker-compose.yml", "docker-compose.yaml"):
                profile.has_docker = True
            elif file in (".github/workflows", ".gitlab-ci.yml", "Jenkinsfile"):
                profile.has_ci_cd = True
            else:
                profile.languages.extend(langs)
                profile.frameworks.extend(frameworks)
                if build_sys and not profile.build_system:
                    profile.build_system = build_sys
                if test_fw and not profile.test_framework:
                    profile.test_framework = test_fw

        if file == "pyproject.toml":
            self._detect_python_frameworks(root, profile)

    def _detect_python_frameworks(self, root: str, profile: RepositoryProfile):
        try:
            toml_path = os.path.join(root, "pyproject.toml")
            if os.path.isfile(toml_path):
                with open(toml_path, encoding="utf-8") as f:
                    content = f.read().lower()
                for pattern, fw_name in _FRAMEWORK_PATTERNS:
                    if pattern in content and fw_name not in profile.frameworks:
                        profile.frameworks.append(fw_name)
        except Exception:
            pass

    @staticmethod
    def _detect_cloud(profile: RepositoryProfile):
        """Detect cloud provider from files."""
        if os.path.isfile("azure-pipelines.yml") or os.path.isfile("azurerm.json"):
            profile.cloud_provider = "azure"
        elif os.path.isfile("buildspec.yml") or os.path.isfile("aws-config.json"):
            profile.cloud_provider = "aws"
        elif os.path.isfile("cloudbuild.yaml") or os.path.isfile("app.yaml"):
            profile.cloud_provider = "gcp"

    @staticmethod
    def _detect_architecture(profile: RepositoryProfile):
        """Heuristic for architecture pattern."""
        if os.path.isdir("services") or os.path.isdir("microservices"):
            profile.architecture_pattern = "microservices"
        elif os.path.isdir("packages") or os.path.isdir("modules"):
            profile.architecture_pattern = "modular-monolith"

    @staticmethod
    def _deduplicate(profile: RepositoryProfile):
        profile.languages = list(dict.fromkeys(profile.languages))
        profile.frameworks = list(dict.fromkeys(profile.frameworks))
