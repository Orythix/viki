"""Unit tests for Frontier Advanced Engineering features."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from viki.core.autonomous_incident_healer import AutonomousIncidentHealer
from viki.skills.builtins.ast_codemod_skill import ASTCodemodSkill
from viki.skills.builtins.openapi_schema_skill import OpenAPISchemaSkill


@pytest.mark.asyncio
async def test_autonomous_incident_healer():
    controller = MagicMock()
    healer = AutonomousIncidentHealer(controller)

    sample_trace = """
Traceback (most recent call last):
  File "viki/core/react_loop.py", line 120, in run_react_loop
    raise ValueError("Invalid state encountered")
ValueError: Invalid state encountered
"""

    incident = healer.parse_stack_trace(sample_trace)
    assert incident["error_type"] == "ValueError"
    assert "Invalid state" in incident["error_msg"]
    assert "react_loop.py" in incident["file_path"]

    res = await healer.auto_heal_incident(sample_trace)
    assert res["status"] == "healed_and_verified"
    assert res["verified"] is True


@pytest.mark.asyncio
async def test_ast_codemod_skill():
    skill = ASTCodemodSkill()
    res = await skill.execute(
        {
            "migration_type": "pydantic_v1_to_v2",
            "target_code": "data = user.dict()\nclass User(BaseModel):\n    pass\n",
        }
    )
    assert ".model_dump()" in res
    assert "AST verified" in res


@pytest.mark.asyncio
async def test_openapi_schema_skill():
    skill = OpenAPISchemaSkill()
    res_json = await skill.execute({"format": "openapi_31_json", "service_name": "TestService"})
    parsed = json.loads(res_json)
    assert parsed["openapi"] == "3.1.0"
    assert parsed["info"]["title"] == "TestService"

    proto_res = await skill.execute({"format": "grpc_proto", "service_name": "TestService"})
    assert 'syntax = "proto3";' in proto_res
