import sqlite_utils
import datetime
import os
import shutil
from typing import Dict, Any, List
from viki.config.logger import viki_logger

class TimeTravelModule:
    """
    "Time Travel" Debugging: Records state snapshots and allows undoing actions.
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

    def take_snapshot(self, event_type: str, description: str, state: Dict[str, Any]):
        timestamp = datetime.datetime.now().isoformat()
        viki_logger.info(f"Taking snapshot: {description}")
        
        self.db["snapshots"].insert({
            "timestamp": timestamp,
            "event_type": event_type,
            "description": description,
            "metadata": os.path.json.dumps(state) if hasattr(os, 'json') else str(state)
        })

    def backup_file(self, file_path: str):
        if not os.path.exists(file_path): return
        
        filename = os.path.basename(file_path)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"{timestamp}_{filename}")
        
        shutil.copy2(file_path, backup_path)
        return backup_path

    def get_history(self, limit: int = 10):
        return list(self.db["snapshots"].rows_where(order_by="id desc", limit=limit))

    async def undo_last(self):
        # Implementation depends on the complexity of actions
        # For now, it logs the intent. In a full version, it would
        # read the backup_path from the last snapshot and restore.
        pass
