"""
QA learning framework — reusable API client and config for the labs/security-lab API.

This package is intentionally small: learn patterns here, then scale to your employer's stack.
"""

from qa_lab.client import SecurityLabClient
from qa_lab.config import Settings

__all__ = ["SecurityLabClient", "Settings"]
