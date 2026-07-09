"""Version information for VIKI — managed by setuptools-scm via git tags."""

from __future__ import annotations

try:
    from ._version_git import version as __version__
except ImportError:
    __version__ = "8.3.0"  # fallback when not installed via pip

__version_info__ = tuple(int(x) for x in __version__.split(".")[:3])
