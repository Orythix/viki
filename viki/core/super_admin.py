import yaml
import os
import datetime
from viki.config.logger import viki_logger

class SuperAdminLayer:
    def __init__(self, config_path: str = "./viki/config/admin.yaml"):
        self.config = {}
        self.config_path = config_path
        self._load_config()
        self.shutdown_triggered = False

    def _load_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    self.config = yaml.safe_load(f)
        except Exception:
            pass

    def check_command(self, user_input: str) -> bool:
        if self.shutdown_triggered: return True
        if not user_input.startswith("ADMIN "): return False

        parts = user_input.strip().split()
        if len(parts) < 4: return False
            
        admin_id, secret, command = parts[1], parts[2], parts[3].upper()
        
        if admin_id == self.config.get("admin_id") and secret == self.config.get("admin_secret"):
            self._execute_kill_switch(command)
            return True
        return False

    def _execute_kill_switch(self, command: str):
        self._log_event(f"SUPER ADMIN COMMAND: {command}")
        if command in ["SHUTDOWN", "KILL", "PAUSE", "DISABLE"]:
            self.shutdown_triggered = True
            viki_logger.critical(f"SUPER ADMIN OVERRIDE: {command}")
            # The controller will handle the actual stop based on the return value

    def _log_event(self, message: str):
        log_path = self.config.get("logs_path", "./data/admin_logs.txt")
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, 'a') as f:
                f.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
        except (IOError, OSError) as e:
            viki_logger.warning(f"Failed to write admin log: {e}")
