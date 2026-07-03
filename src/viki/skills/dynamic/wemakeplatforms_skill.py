import json
from typing import Any

from viki.skills.base import BaseSkill


class WeMakePlatformsSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "wemakeplatforms_team"

    @property
    def description(self) -> str:
        return "Query information about the We Make Platforms team and their roles."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional. Specific team member name or role to look up. E.g. 'President', 'Asela', or 'all'.",
                }
            },
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    @property
    def triggers(self) -> list[str]:
        return ["wemakeplatforms", "we make platforms team", "wmp team"]

    async def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        query = params.get("query", "all").lower()

        # TODO: Replace with your own team data or remove this skill
        team_data = [
            {
                "name": "Example User 1",
                "role": "Software Engineer",
                "description": "Example team member profile — customize for your organization.",
            },
            {
                "name": "Example User 2",
                "role": "Technical Lead",
                "description": "Example team member profile — customize for your organization.",
            },
        ]

        if query == "all" or not query:
            return json.dumps({"team": team_data}, indent=2)

        results = [
            member
            for member in team_data
            if query in member["name"].lower() or query in member["role"].lower()
        ]

        if results:
            return json.dumps({"team": results}, indent=2)
        else:
            return f"No team members found matching query: '{query}'"
