import sqlite_utils
import datetime
import os
import json
import shutil
import uuid
from typing import Dict, Any, List, Optional, Tuple
from viki.config.logger import viki_logger
from viki.core.safety import safe_for_log

class TimeTravelModule:
    """
    "Time Travel" Debugging: Records state snapshots and allows undoing actions.
    Includes checkpointing before file/shell modifications for /restore (Gemini CLI-style).
    """
    def __init__(self, data_dir: str):
        self.db_path = os.path.join(data_dir, "history.db")
        # v21: Explicitly handle multi-threading
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self.db_path, check_same_thread=False)
        self.db = sqlite_utils.Database(conn)
        self.backup_dir = os.path.join(data_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Initialize tables
        if "snapshots" not in self.db.table_names():
            self.db["snapshots"].create({
                "id": int,
                "timestamp": str,
                "event_type": str,
                "description": str,
                "metadata": str # JSON string of state
            }, pk="id")

        if "checkpoints" not in self.db.table_names():
            self.db["checkpoints"].create({
                "id": str,
                "timestamp": str,
                "skill_name": str,
                "params_json": str,
                "conversation_snippet_json": str,
                "backups_json": str,
            }, pk="id")

    def take_snapshot(self, event_type: str, description: str, state: Dict[str, Any]):
        timestamp = datetime.datetime.now().isoformat()
        viki_logger.info(f"Taking snapshot: {description}")
        
        self.db["snapshots"].insert({
            "timestamp": timestamp,
            "event_type": event_type,
            "description": description,
            "metadata": json.dumps(state)
        })

    def backup_file(self, file_path: str) -> Optional[str]:
        if not os.path.exists(file_path):
            return None
        filename = os.path.basename(file_path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"{timestamp}_{filename}")
        shutil.copy2(file_path, backup_path)
        return backup_path

    def get_history(self, limit: int = 10):
        return list(self.db["snapshots"].rows_where(order_by="id desc", limit=limit))

    def create_checkpoint(
        self,
        controller: Any,
        skill_name: str,
        params: Dict[str, Any],
    ) -> str:
        """Create a checkpoint before a file/shell action. Backs up affected files. Returns checkpoint id."""
        cid = str(uuid.uuid4())[:8]
        timestamp = datetime.datetime.now().isoformat()
        trace = controller.memory.working.get_trace()
        snippet = trace[-10:] if len(trace) >= 10 else trace
        conversation_snippet_json = json.dumps([{"role": m.get("role"), "content": (m.get("content") or "")[:500]} for m in snippet])
        params_json = json.dumps(params)

        paths_to_backup = []
        if skill_name in ("dev_tools", "filesystem_skill"):
            path = params.get("path")
            if path and isinstance(path, str):
                path = os.path.abspath(path)
                if os.path.isfile(path):
                    paths_to_backup.append(path)
        elif skill_name == "shell":
            pass  # no file backup; we still store conversation and params

        backups = []
        for orig in paths_to_backup:
            backup_path = self.backup_file(orig)
            if backup_path:
                backups.append({"original": orig, "backup": backup_path})
        backups_json = json.dumps(backups)

        self.db["checkpoints"].insert({
            "id": cid,
            "timestamp": timestamp,
            "skill_name": skill_name,
            "params_json": params_json,
            "conversation_snippet_json": conversation_snippet_json,
            "backups_json": backups_json,
        })
        viki_logger.info(f"Checkpoint {cid} created for {skill_name}")
        return cid

    def list_checkpoints(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            rows = list(self.db["checkpoints"].rows_where(order_by="timestamp desc", limit=limit))
        except Exception:
            rows = list(self.db["checkpoints"].rows)
        if not rows:
            return []
        out = []
        for r in rows:
            try:
                params = json.loads(r.get("params_json") or "{}")
                summary = f"{r.get('skill_name', '?')}"
                if params.get("path"):
                    summary += f" {safe_for_log(str(params.get('path', '')), max_len=40)}"
                if params.get("command"):
                    summary += f" cmd: {safe_for_log(str(params.get('command', '')), max_len=40)}"
                out.append({
                    "id": r.get("id"),
                    "timestamp": r.get("timestamp"),
                    "skill_name": r.get("skill_name"),
                    "summary": summary,
                })
            except (json.JSONDecodeError, TypeError):
                out.append({"id": r.get("id"), "timestamp": r.get("timestamp"), "skill_name": r.get("skill_name"), "summary": "?"})
        return out

    def restore_checkpoint(self, checkpoint_id: str) -> Tuple[bool, List[str], str]:
        """Restore files from a checkpoint. Returns (success, list of restored paths, message)."""
        row = self.db["checkpoints"].get(checkpoint_id)
        if not row:
            return False, [], f"Checkpoint '{checkpoint_id}' not found."
        try:
            backups = json.loads(row.get("backups_json") or "[]")
        except json.JSONDecodeError:
            return False, [], "Checkpoint data invalid."
        restored = []
        for b in backups:
            orig = b.get("original")
            backup = b.get("backup")
            if not orig or not backup:
                continue
            if not os.path.isfile(backup):
                viki_logger.warning(f"Backup file missing: {backup}")
                continue
            try:
                shutil.copy2(backup, orig)
                restored.append(orig)
            except Exception as e:
                viki_logger.error(f"Restore failed for {orig}: {e}")
        return True, restored, f"Restored {len(restored)} file(s) from checkpoint {checkpoint_id}."

    async def undo_last(self):
        # Implementation depends on the complexity of actions
        # For now, it logs the intent. In a full version, it would
        # read the backup_path from the last snapshot and restore.
        pass
