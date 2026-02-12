import os
import ctypes
import subprocess
from typing import List, Dict, Any
from viki.config.logger import viki_logger

class SemanticFS:
    """
    "Semantic Filesystem": Manages a focus folder (Drive V equivalent)
    populated with symlinks based on semantic context.
    """
    def __init__(self, workspace_root: str):
        self.focus_dir = os.path.join(workspace_root, "FOCUS")
        os.makedirs(self.focus_dir, exist_ok=True)

    def clear_focus(self):
        """Clears all existing symlinks in the focus directory."""
        viki_logger.info("Clearing Semantic FS Focus...")
        for filename in os.listdir(self.focus_dir):
            file_path = os.path.join(self.focus_dir, filename)
            try:
                if os.path.islink(file_path) or os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    os.rmdir(file_path)
            except Exception as e:
                viki_logger.error(f"Failed to delete {file_path}: {e}")

    def mount_context(self, file_paths: List[str]):
        """Creates symlinks for the given file paths in the focus directory."""
        viki_logger.info(f"Mounting {len(file_paths)} files into Semantic FS...")
        self.clear_focus()
        
        for path in file_paths:
            if not os.path.exists(path): continue
            
            filename = os.path.basename(path)
            link_path = os.path.join(self.focus_dir, filename)
            
            try:
                # On Windows, creating symlinks needs 'mklink' or os.symlink (with dev mode)
                # We'll try os.symlink first
                os.symlink(path, link_path)
            except OSError:
                # Fallback to creating a Windows shortcut (.url or .lnk) or shell command
                try:
                    # Shell command for Hard Link or Junction if privilege fails
                    if os.path.isdir(path):
                        subprocess.run(['mklink', '/J', link_path, path], shell=True, capture_output=True)
                    else:
                        subprocess.run(['mklink', link_path, path], shell=True, capture_output=True)
                except Exception as e:
                    viki_logger.error(f"Failed to mount {path}: {e}")
        
        return self.focus_dir
