import os
import shutil
from typing import Dict, Any, List, Optional
from viki.skills.base import BaseSkill

class DevSkill(BaseSkill):
    """
    Development capabilities: File system exploration, reading, writing, and patching code.
    """
    @property
    def name(self) -> str:
        return "dev_tools"

    @property
    def description(self) -> str:
        return (
            "Developer tools. Usage:\n"
            "- list_files(path='.')\n"
            "- read_file(path='file.py')\n"
            "- write_file(path='file.py', content='...')\n"
            "- patch_file(path='file.py', target='old', replacement='new')"
        )

    async def execute(self, params: Dict[str, Any]) -> str:
        path = params.get('path', '.')
        if not path:
            path = '.'
            
        # Determine intent based on params
        if 'target' in params and 'replacement' in params:
             return self._patch_file(path, params['target'], params['replacement'])
        elif 'content' in params:
             return self._write_file(path, params['content'])
        elif params.get('mode') == 'list' or os.path.isdir(path):
             return self._list_files(path)
        else:
             return self._read_file(path)

    def _list_files(self, path: str) -> str:
        try:
            if not os.path.exists(path):
                return f"Error: Path '{path}' not found."
            items = os.listdir(path)
            annotated = [f"[{'DIR' if os.path.isdir(os.path.join(path, i)) else 'FILE'}] {i}" for i in items]
            return f"CONTENTS OF {path}:\n" + "\n".join(annotated)
        except Exception as e:
            return f"List Error: {e}"

    def _read_file(self, path: str) -> str:
        try:
            if not os.path.exists(path):
                return f"Error: File '{path}' not found."
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return f"--- FILE: {path} ---\n{content}\n--- END FILE ---"
        except Exception as e:
            return f"Read Error: {e}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content.replace("\\n", "\n"))
            return f"Successfully wrote to {path}."
        except Exception as e:
            return f"Write Error: {e}"

    def _patch_file(self, path: str, target: str, replacement: str) -> str:
        try:
            if not os.path.exists(path): return f"Error: File '{path}' not found."
            with open(path, 'r', encoding='utf-8') as f: content = f.read()
            target = target.replace("\\n", "\n")
            replacement = replacement.replace("\\n", "\n")
            if target not in content: return f"Error: Target text not found in {path}."
            new_content = content.replace(target, replacement)
            self._backup_file(path)
            with open(path, 'w', encoding='utf-8') as f: f.write(new_content)
            return f"Successfully patched {path}."
        except Exception as e:
            return f"Patch Error: {e}"

    def _backup_file(self, path: str):
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
