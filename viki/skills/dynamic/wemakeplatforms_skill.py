import json
from typing import Dict, Any, List
from viki.skills.base import BaseSkill

class WeMakePlatformsSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "wemakeplatforms_team"

    @property
    def description(self) -> str:
        return "Query information about the We Make Platforms team and their roles."

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Optional. Specific team member name or role to look up. E.g. 'President', 'Asela', or 'all'."
                }
            }
        }

    @property
    def safety_tier(self) -> str:
        return "safe"

    @property
    def triggers(self) -> List[str]:
        return ["wemakeplatforms", "we make platforms team", "wmp team"]

    async def execute(self, params: Dict[str, Any] = None) -> str:
        params = params or {}
        query = params.get("query", "all").lower()

        team_data = [
            {"name": "Dave Morris", "role": "President - Puerto Rico", "description": "17+ years in eCommerce and software development, business growth, sales strategy."},
            {"name": "Asela Neligama", "role": "Managing Director - Sri Lanka", "description": "18+ years in software solutions for e-Commerce, Health-care, Reservations, Classifieds."},
            {"name": "Supun Perumbuli", "role": "Technology Director - Sri Lanka", "description": "18+ years in scalable, secure backend, frontend and mobile systems, cloud-native applications."},
            {"name": "Peshala A.", "role": "Product Manager", "description": "15+ years in Business Analysis, Project Management and Solution Consulting."},
            {"name": "Namal F.", "role": "Software Architect (Full-stack)", "description": "14+ years in Java, J2EE, Spring, Angular, SQL, NoSQL, Kafka."},
            {"name": "Harshana K.", "role": "Technical Lead (Full-stack)", "description": "7+ years in scalable, high-performance web and hybrid mobile apps."},
            {"name": "Naveen D.", "role": "Senior Technical Lead (Front-end)", "description": "Decade of experience in Angular, Ionic, WordPress."},
            {"name": "Nalin B.", "role": "Senior Technical Lead (Full-stack)", "description": "16+ years in Java, Spring, Hibernate, Node.js, Angular, React."},
            {"name": "Sachithra C.", "role": "Technical Lead (Full-stack)", "description": "8 years in Transport, Cargo, E-commerce, Finance. Java, Spring Boot, Angular, React, Flutter."},
            {"name": "Nirosha J.", "role": "Technical Lead (Full-stack)", "description": "5 years in Java, Spring Boot, Microservices, Angular, React."},
            {"name": "Sachin D.", "role": "Technical Lead (Front-end)", "description": "5+ years in Angular, React.js, Vue.js, Next.js, PHP."},
            {"name": "Kosala Liyanage", "role": "Lead UI/UX Designer", "description": "Decade of experience in healthcare, education, e-commerce, reservations, payment processing."}
        ]

        if query == "all" or not query:
            return json.dumps({"team": team_data}, indent=2)

        results = [
            member for member in team_data 
            if query in member["name"].lower() or query in member["role"].lower()
        ]

        if results:
            return json.dumps({"team": results}, indent=2)
        else:
            return f"No team members found matching query: '{query}'"
