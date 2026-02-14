import yaml
import os
import datetime
import secrets
from viki.config.logger import viki_logger

class SuperAdminLayer:
    def __init__(self, config_path: str = "./viki/config/admin.yaml"):
        self.config = {}
        self.config_path = config_path
        self._load_config()
        self.shutdown_triggered = False
        
        # Load admin_secret from environment variable (more secure)
        self.admin_secret = os.getenv('VIKI_ADMIN_SECRET')
        if not self.admin_secret:
            # Fallback to config file (deprecated)
            self.admin_secret = self.config.get("admin_secret", "")
            if not self.admin_secret or self.admin_secret == "CHANGE_THIS_SECRET_IMMEDIATELY_XYZ123":
                # Generate a secure random secret
                self.admin_secret = secrets.token_urlsafe(32)
                viki_logger.warning(f"No VIKI_ADMIN_SECRET set. Generated temporary admin secret: {self.admin_secret}")
                viki_logger.warning("Set VIKI_ADMIN_SECRET environment variable for persistent admin access.")

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
        
        if admin_id == self.config.get("admin_id") and secret == self.admin_secret:
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
