"""
Path sandbox for content-creation and file-writing skills.
Ensures output paths stay under allowed roots and not under blocked system paths.
"""
import os
from typing import List, Optional, Tuple, Any

# System directories that must not be written to
BLOCKED_PATHS = [
    "C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)",
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc",
]


def get_allowed_roots(controller: Any = None) -> List[str]:
    """Return list of allowed root directories for output files."""
    roots = []
    if controller and getattr(controller, "settings", None):
        system = controller.settings.get("system", {})
        for key in ("workspace_dir", "data_dir"):
            val = system.get(key)
            if val:
                roots.append(os.path.abspath(os.path.expanduser(val)))
    if not roots:
        roots.append(os.path.abspath(os.getcwd()))
        data = os.environ.get("VIKI_DATA_DIR") or os.path.join(os.getcwd(), "data")
        workspace = os.environ.get("VIKI_WORKSPACE_DIR") or os.path.join(os.getcwd(), "workspace")
        roots.append(os.path.abspath(data))
        roots.append(os.path.abspath(workspace))
    return list(dict.fromkeys(roots))  # dedupe preserving order


def validate_output_path(
    path: str,
    allowed_roots: Optional[List[str]] = None,
    blocked_paths: Optional[List[str]] = None,
    controller: Any = None,
) -> Tuple[bool, str]:
    """
    Validate that path resolves under an allowed root and not under a blocked path.
    Returns (True, real_path) or (False, error_message).
    """
    if not path or not str(path).strip():
        return False, "Path is empty."
    blocked = blocked_paths if blocked_paths is not None else BLOCKED_PATHS
    roots = allowed_roots if allowed_roots is not None else get_allowed_roots(controller)
    try:
        real_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    except Exception as e:
        return False, f"Invalid path: {e}"
    for bp in blocked:
        try:
            if real_path.startswith(os.path.realpath(bp)):
                return False, f"Access denied: path is in a protected system directory."
        except Exception:
            continue
    for root in roots:
        try:
            if real_path.startswith(os.path.realpath(root)):
                return True, real_path
        except Exception:
            continue
    return False, "Access denied: path is outside allowed directories (workspace, data)."
