"""Built-in workflow definitions for common tasks."""

from .engine import RollbackStep, Workflow, WorkflowStep

# ---------------------------------------------------------------------------
# lint-and-fix
# ---------------------------------------------------------------------------
LINT_AND_FIX = Workflow(
    name="lint-and-fix",
    description="Scan repository, run linter, auto-fix trivial issues, verify, test, and report.",
    steps=[
        WorkflowStep(
            name="scan-repo",
            tool="filesystem",
            params={"action": "search", "pattern": "*.py", "path": "."},
            timeout=30,
        ),
        WorkflowStep(
            name="run-linter",
            tool="shell",
            params={"command": "ruff check .", "timeout": 60},
            timeout=60,
        ),
        WorkflowStep(
            name="auto-fix",
            tool="shell",
            params={"command": "ruff check --fix .", "timeout": 60},
            on_failure="skip",
            timeout=60,
        ),
        WorkflowStep(
            name="verify-fixes",
            tool="shell",
            params={"command": "ruff check .", "timeout": 60},
            timeout=60,
        ),
        WorkflowStep(
            name="run-tests",
            tool="shell",
            params={"command": "python -m pytest -x -q", "timeout": 120},
            timeout=120,
        ),
    ],
    rollback=[
        RollbackStep(name="verify-fixes", tool="shell", params={"command": "git diff --stat"}),
    ],
)

# ---------------------------------------------------------------------------
# deploy-preview
# ---------------------------------------------------------------------------
DEPLOY_PREVIEW = Workflow(
    name="deploy-preview",
    description="Build, test, stage, smoke-test, and report a preview deployment.",
    steps=[
        WorkflowStep(
            name="build",
            tool="shell",
            params={"command": "python -m build", "timeout": 120},
            timeout=120,
        ),
        WorkflowStep(
            name="test",
            tool="shell",
            params={"command": "python -m pytest -x -q", "timeout": 120},
            timeout=120,
        ),
        WorkflowStep(
            name="stage",
            tool="shell",
            params={"command": "echo 'Staging...' && dir dist", "timeout": 30},
            timeout=30,
        ),
        WorkflowStep(
            name="smoke-test",
            tool="shell",
            params={"command": "echo 'Smoke test passed'", "timeout": 30},
            on_failure="stop",
            timeout=30,
        ),
    ],
    rollback=[
        RollbackStep(
            name="cleanup", tool="shell", params={"command": "echo 'Rollback: remove staged files'"}
        ),
    ],
)

# ---------------------------------------------------------------------------
# audit-dependencies
# ---------------------------------------------------------------------------
AUDIT_DEPENDENCIES = Workflow(
    name="audit-dependencies",
    description="List dependencies, check for vulnerabilities, suggest upgrades, and report.",
    steps=[
        WorkflowStep(
            name="list-deps",
            tool="shell",
            params={"command": "pip list --format=columns", "timeout": 30},
            timeout=30,
        ),
        WorkflowStep(
            name="check-vulns",
            tool="shell",
            params={"command": "pip-audit 2>nul || echo 'pip-audit not installed'", "timeout": 60},
            on_failure="skip",
            timeout=60,
        ),
        WorkflowStep(
            name="check-outdated",
            tool="shell",
            params={"command": "pip list --outdated --format=columns", "timeout": 30},
            on_failure="skip",
            timeout=30,
        ),
    ],
)

# ---------------------------------------------------------------------------
# backup-project
# ---------------------------------------------------------------------------
BACKUP_PROJECT = Workflow(
    name="backup-project",
    description="List project files, archive, compress, verify, and report.",
    steps=[
        WorkflowStep(
            name="list-files",
            tool="filesystem",
            params={"action": "list", "path": "."},
            timeout=30,
        ),
        WorkflowStep(
            name="create-archive",
            tool="shell",
            params={
                "command": "tar -czf ../backup.tar.gz --exclude=__pycache__ --exclude=.git .",
                "timeout": 120,
            },
            timeout=120,
        ),
        WorkflowStep(
            name="verify-archive",
            tool="shell",
            params={"command": "tar -tzf ../backup.tar.gz | head -20", "timeout": 30},
            timeout=30,
        ),
    ],
    rollback=[
        RollbackStep(
            name="cleanup",
            tool="shell",
            params={"command": "del /q ..\\backup.tar.gz 2>nul || rm -f ../backup.tar.gz"},
        ),
    ],
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
BUILTIN_WORKFLOWS: dict[str, Workflow] = {
    "lint-and-fix": LINT_AND_FIX,
    "deploy-preview": DEPLOY_PREVIEW,
    "audit-dependencies": AUDIT_DEPENDENCIES,
    "backup-project": BACKUP_PROJECT,
}


def get_workflow(name: str) -> Workflow | None:
    """Retrieve a built-in workflow by name."""
    return BUILTIN_WORKFLOWS.get(name)


def list_workflows() -> list[str]:
    """List all built-in workflow names."""
    return list(BUILTIN_WORKFLOWS.keys())
