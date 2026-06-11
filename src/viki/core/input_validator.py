"""Pydantic-based input validation for CLI and API entry points."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator


class UserInput(BaseModel):
    """Validated user input for VIKI processing."""

    text: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=100_000,
            strip_whitespace=True,
        ),
    ]

    @model_validator(mode="after")
    def check_control_chars(self) -> UserInput:
        """Reject raw control characters except newlines and tabs."""
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", self.text)
        if cleaned != self.text:
            self.text = cleaned
        return self


class QueryInput(BaseModel):
    """Validated single-query input."""

    text: Annotated[
        str,
        StringConstraints(
            min_length=1,
            max_length=50_000,
            strip_whitespace=True,
        ),
    ]

    workspace: Annotated[
        str | None,
        StringConstraints(max_length=500),
    ] = None


def validate_user_input(raw: str) -> str | None:
    """Validate and sanitize user input. Returns None if invalid."""
    try:
        validated = UserInput(text=raw)
        return validated.text
    except Exception:
        return None


def validate_query(raw: str, workspace: str | None = None) -> str | None:
    """Validate single query input. Returns None if invalid."""
    try:
        validated = QueryInput(text=raw, workspace=workspace)
        return validated.text
    except Exception:
        return None
