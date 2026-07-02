"""Compatibility shims for supported Python versions (3.10+).

``enum.StrEnum`` was added in Python 3.11. On 3.10 we provide an
equivalent with identical ``str()``/``format()`` semantics.
"""

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of enum.StrEnum: members are strings equal to their value."""

        def __str__(self) -> str:
            return str.__str__(self)

        def __format__(self, format_spec: str) -> str:
            return str.__format__(self, format_spec)


__all__ = ["StrEnum"]
