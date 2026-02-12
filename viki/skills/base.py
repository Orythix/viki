from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseSkill(ABC):
    """Abstract base class for all VIKI skills."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of what the skill does."""
        pass

    @property
    def version(self) -> str:
        """Skill version for contract stability."""
        return "1.0.0"

    @property
    def schema(self) -> Dict[str, Any]:
        """JSON-schema like representation of input parameters.
        Override this in subclasses to enable native tool/function calling.
        
        Example:
            return {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play_pause", "next_track", "volume_up"],
                        "description": "The media action to perform"
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Amount (e.g., volume steps)",
                        "default": 5
                    }
                },
                "required": ["action"]
            }
        """
        return {}

    @property
    def safety_tier(self) -> str:
        """Safe, Medium, or Destructive."""
        return "safe"

    @property
    def triggers(self) -> List[str]:
        """List of keywords or regex triggers for this skill."""
        return []

    def get_tool_definition(self) -> Dict[str, Any]:
        """Generate an Ollama/OpenAI-compatible tool definition.
        Returns a dict in the format expected by the `tools` parameter.
        Only generates a definition if the skill has a non-empty schema.
        """
        param_schema = self.schema
        if not param_schema:
            # No schema defined — generate a minimal one from description
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": param_schema
            }
        }

    @abstractmethod
    async def execute(self, params: Dict[str, Any]) -> str:
        """Execute the skill with the given parameters asynchronously."""
        pass
