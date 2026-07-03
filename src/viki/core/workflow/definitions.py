"""Built-in workflow definitions."""

from __future__ import annotations

from .engine import RollbackStep, Workflow, WorkflowStep

_BUILTIN_WORKFLOWS: dict[str, Workflow] = {
    "lint-and-fix": Workflow(
        name="lint-and-fix",
        description="Run linter and auto-fix issues in the project.",
        steps=[
            WorkflowStep(name="run-linter", tool="dev", params={"action": "lint"}, timeout=120),
            WorkflowStep(
                name="apply-fixes", tool="dev", params={"action": "fix"}, timeout=120, retry_count=1
            ),
        ],
        rollback=[
            RollbackStep(name="restore-backup", tool="git", params={"action": "restore"}),
        ],
    ),
    "deploy-preview": Workflow(
        name="deploy-preview",
        description="Build and deploy a preview environment.",
        steps=[
            WorkflowStep(
                name="install-deps", tool="shell", params={"command": "npm ci"}, timeout=300
            ),
            WorkflowStep(
                name="build", tool="shell", params={"command": "npm run build"}, timeout=300
            ),
            WorkflowStep(
                name="deploy", tool="shell", params={"command": "npx vercel --preview"}, timeout=120
            ),
        ],
        rollback=[
            RollbackStep(
                name="remove-deploy", tool="shell", params={"command": "npx vercel --remove"}
            ),
        ],
    ),
    "audit-dependencies": Workflow(
        name="audit-dependencies",
        description="Audit project dependencies for known vulnerabilities.",
        steps=[
            WorkflowStep(name="audit", tool="shell", params={"command": "npm audit"}, timeout=120),
        ],
    ),
    "backup-project": Workflow(
        name="backup-project",
        description="Create a git backup branch and push to remote.",
        steps=[
            WorkflowStep(
                name="create-branch",
                tool="git",
                params={"action": "branch", "name": "backup/auto"},
                timeout=30,
            ),
            WorkflowStep(
                name="commit",
                tool="git",
                params={"action": "commit", "message": "Auto-backup"},
                timeout=30,
            ),
            WorkflowStep(name="push", tool="git", params={"action": "push"}, timeout=60),
        ],
        rollback=[
            RollbackStep(
                name="delete-branch",
                tool="git",
                params={"action": "delete-branch", "name": "backup/auto"},
            ),
        ],
    ),
}


def list_workflows() -> list[str]:
    """Return names of all built-in workflows."""
    return list(_BUILTIN_WORKFLOWS.keys())


def get_workflow(name: str) -> Workflow | None:
    """Return a workflow by name, or None if not found."""
    return _BUILTIN_WORKFLOWS.get(name)
