from typing import Any

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class MarketExplorerSkill(BaseSkill):
    """
    MarketExplorerSkill: A high-level orchestrator that demonstrates Multi-Tool Synergy.
    It combines web research, sandboxed data analysis, and report generation.
    """

    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "market_explorer"

    @property
    def description(self) -> str:
        return "End-to-end market research agent. Browses, analyzes, and reports automatically."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The market research topic (e.g., 'AI chip trends 2024')",
                },
                "output_file": {
                    "type": "string",
                    "default": "market_report.md",
                    "description": "Path to save the final report.",
                },
            },
            "required": ["topic"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        topic = params.get("topic")
        output_file = params.get("output_file", "market_report.md")

        if not self._controller:
            return "Error: Controller is required for tool synergy."

        viki_logger.info(f"MarketExplorer: Starting deep research on '{topic}'...")

        try:
            # 1. BROWSE: Get data via ResearchSkill
            research_skill = self._controller.skill_registry.get_skill("research")
            if not research_skill:
                return "Error: research_skill not found."

            search_results = await research_skill.execute({"query": topic})

            # 2. ANALYZE: Use ManusSkill for sandboxed processing
            manus_skill = self._controller.skill_registry.get_skill("manus")
            if not manus_skill:
                return f"MarketExplorer: Manus not found. Returning raw search data instead.\n\n{search_results}"

            viki_logger.info("MarketExplorer: Sending data to Manus for analysis...")
            analysis_task = (
                f"Analyze the following search results about '{topic}'. "
                "Identify top 3 trends and 2 risks. "
                f"Data:\n{search_results[:2000]}"
            )
            analysis_report = await manus_skill.execute({"task": analysis_task})

            # 3. REPORT: Save via FileSystemSkill
            fs_skill = self._controller.skill_registry.get_skill("filesystem_skill")
            if fs_skill:
                await fs_skill.execute(
                    {
                        "action": "write_file",
                        "path": output_file,
                        "content": f"# Market Research Report: {topic}\n\n{analysis_report}",
                    }
                )
                return f"COMPLETED: Market research for '{topic}' finalized. Report saved to {output_file}."

            return f"COMPLETED: Market research for '{topic}' finalized.\n\n{analysis_report}"

        except Exception as e:
            viki_logger.error(f"MarketExplorer Error: {e}")
            return f"Market Research Failed: {str(e)}"
