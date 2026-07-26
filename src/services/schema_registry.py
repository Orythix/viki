import json
from typing import Dict, Any, List, Tuple, Union
# Using Pydantic or similar for robust schema definition would be ideal here.

class SchemaRegistry:
    """
    Central repository for all data schemas used across VIKI's pipelines. 
    Loads and manages validation rulesets based on source and entity type.
    """
    _schemas: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register_schema(cls, schema_key: str, schema_definition: Dict[str, Any]):
        """Registers a new schema definition."""
        if schema_key in cls._schemas:
            print(f"Warning: Overwriting existing schema for key: {schema_key}")
        cls._schemas[schema_key] = schema_definition

    @classmethod
    def get_schema(cls, schema_key: str) -> Union[Dict[str, Any], None]:
        """Retrieves a registered schema."""
        return cls._schemas.get(schema_key)

# --- Initial Schema Registration (Bootstrap) ---
# Registering the core SKG structure for initial validation checks
SCHEMA_CORE = {
    "entity": ["Skill", "Concept", "Process", "User", "SourceDocument"],
    "relationship": ["REQUIRES", "IS_A_TYPE_OF", "REFERENCES", "IS_DOCUMENTED_IN", "ACTS_UPON"]
}

# Registering a schema for the KnowledgeIngestor's output (Triples)
SCHEMA_TRIPLES = {
    "required": ["subject", "predicate", "object"],
    "types": {"subject": str, "predicate": str, "object": str},
    "constraints": {"predicate": lambda p: p in SCHEMA_CORE["relationship"]}
}

# Registering a schema for Usage Logs (JSONL)
SCHEMA_USAGE_LOG = {
    "required": ["session_id", "event", "prompt"],
    "types": {"session_id": str, "event": str, "prompt": str},
    "constraints": {"event": lambda e: e in ["llm_inference", "api_call"]}
}

SchemaRegistry.register_schema("triples", SCHEMA_TRIPLES)
SchemaRegistry.register_schema("usage_log", SCHEMA_USAGE_LOG)
# ...existing code...