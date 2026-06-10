import os
from typing import List
from viki.domain.entities.health import HealthIssue
from viki.config.logger import viki_logger

class SelfHealingService:
    def __init__(self, controller):
        self.controller = controller
        self.detected_issues: List[HealthIssue] = []

    async def analyze_file(self, file_path: str):
        """Analyze a file for potential health issues (lint, complexity, bugs)."""
        if not file_path.endswith('.py'):
            return

        viki_logger.info(f"Self-Healing: Analyzing {file_path} for potential improvements...")
        
        # Simple heuristic for now: check for 'TODO' or 'FIXME'
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'TODO' in content or 'FIXME' in content:
                    issue = HealthIssue(
                        id=f"HEAL-{os.path.basename(file_path)}-{len(self.detected_issues)}",
                        severity="low",
                        file_path=file_path,
                        description="File contains TODO or FIXME markers.",
                        suggestion="Consider addressing pending tasks to improve code health."
                    )
                    self.detected_issues.append(issue)
                    await self._notify_user(issue)
        except Exception as e:
            viki_logger.error(f"Self-Healing analysis failed for {file_path}: {e}")

    async def _notify_user(self, issue: HealthIssue):
        """Proactively notify the user via Nexus if an issue is found."""
        if not hasattr(self.controller, "nexus"):
            return

        msg = (
            f"🩺 **Self-Healing Alert**: I found a potential improvement in `{os.path.basename(issue.file_path)}`.\n"
            f"**Issue**: {issue.description}\n"
            f"**Suggestion**: {issue.suggestion}\n"
            f"Would you like me to attempt a fix? (/fix {issue.id} or /ignore)"
        )
        
        await self.controller.nexus.ingest(
            source="System",
            user_id="SelfHealing",
            text=msg,
            priority=20
        )
