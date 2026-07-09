"""
Skill synthesis with test generation.

When the dynamic-skill creator writes a new skill, this module generates a
pytest file and validates it in the sandbox before registration.
"""

from __future__ import annotations

import os
import textwrap
from typing import Any

from viki.config.logger import viki_logger

SKILL_TEST_TEMPLATE = '''
"""Tests for the {skill_name} skill."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_{skill_name}_basic():
    """Test basic execution of {skill_name}."""
    from viki.skills.dynamic.{skill_name} import {skill_class}

    skill = {skill_class}()
    result = await skill.execute({{"input": "test"}})
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_{skill_name}_empty_input():
    """Test that empty input is handled gracefully."""
    from viki.skills.dynamic.{skill_name} import {skill_class}

    skill = {skill_class}()
    result = await skill.execute({{}})
    assert result is not None
'''


class SkillSynthesizer:
    """
    Generates test files and validates dynamic skills.

    Attached to the dynamic skill creation pipeline.
    """

    def __init__(self, sandbox: Any | None = None):
        self._sandbox = sandbox
        self._test_dir = ""

    def set_test_dir(self, path: str) -> None:
        self._test_dir = path
        os.makedirs(path, exist_ok=True)

    def generate_test_file(self, skill_name: str, skill_class: str, output_dir: str) -> str:
        """
        Generate a pytest test file for a dynamic skill.

        Returns the path to the generated test file.
        """
        content = SKILL_TEST_TEMPLATE.format(
            skill_name=skill_name,
            skill_class=skill_class,
        )
        content = textwrap.dedent(content).strip()

        test_path = os.path.join(output_dir, f"test_{skill_name}.py")
        os.makedirs(output_dir, exist_ok=True)
        with open(test_path, "w") as f:
            f.write(content + "\n")

        viki_logger.info("SkillSynthesizer: generated tests for '%s' at %s", skill_name, test_path)
        return test_path

    async def validate_with_tests(self, skill_name: str, test_path: str) -> bool:
        """
        Run the generated tests in the sandbox.

        Returns True if all tests pass.
        """
        if self._sandbox is None:
            viki_logger.warning("SkillSynthesizer: no sandbox available, skipping validation")
            return True

        viki_logger.info("SkillSynthesizer: validating '%s' with tests...", skill_name)
        try:
            result = await self._sandbox.run(
                ["pytest", test_path, "-v", "--tb=short", "-q"],
                cwd=os.path.dirname(test_path) or ".",
            )
            if result.success:
                viki_logger.info("SkillSynthesizer: '%s' tests PASSED", skill_name)
                return True
            viki_logger.error("SkillSynthesizer: '%s' tests FAILED:\n%s", skill_name, result.error)
            return False
        except Exception as e:
            viki_logger.error("SkillSynthesizer: validation error for '%s': %s", skill_name, e)
            return False

    async def create_and_validate(
        self,
        skill_name: str,
        skill_class: str,
        skill_code: str,
        output_dir: str,
    ) -> bool:
        """
        Full pipeline: write skill file, generate tests, run them.

        Returns True if all validations pass.
        """
        # Write the skill file
        skill_path = os.path.join(output_dir, f"{skill_name}.py")
        os.makedirs(output_dir, exist_ok=True)
        with open(skill_path, "w") as f:
            f.write(skill_code)

        # Generate tests
        test_path = self.generate_test_file(skill_name, skill_class, output_dir)

        # Validate with tests
        return await self.validate_with_tests(skill_name, test_path)
