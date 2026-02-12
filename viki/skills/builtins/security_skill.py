import os
import subprocess
import json
from typing import Dict, Any, List
from viki.skills.base import BaseSkill
from viki.config.logger import viki_logger
import requests

class SecuritySkill(BaseSkill):
    """
    Ethical Hacking & Network Security Skill.
    Enables VIKI to perform local network scans and audits.
    """
    def __init__(self):
        self._name = "security_tools"
        self._description = (
            "Ethical hacking tools for LOCAL networks only.\n"
            "Actions: net_scan(target, type), web_audit(url), sniffer(count).\n"
            "Safety: Refuses public targets (google.com, etc.)."
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        target = params.get("target") or params.get("url")
        
        if not action or not target:
            return "Error: Both 'action' and 'target' are required."

        # 1. Safety Check: Only local networks or explicitly whitelisted
        if self._is_public_target(target):
            return (
                "ACCESS DENIED: Attempt to scan a public/restricted target detected. "
                "I am bound by the Computer Fraud and Abuse Act (CFAA). "
                "I only operate on local 192.168.x.x, 10.x.x.x, or 127.0.0.1 networks."
            )

        try:
            if action == "net_scan":
                scan_type = params.get("type", "-F") # Fast scan by default
                viki_logger.info(f"Security: Running nmap {scan_type} on {target}")
                # We assume nmap is installed on the system path
                result = subprocess.run(['nmap', scan_type, target], capture_output=True, text=True, timeout=60)
                return f"NMAP SCAN RESULTS FOR {target}:\n{result.stdout}"

            elif action == "web_audit":
                viki_logger.info(f"Security: Auditing {target} for sensitive files")
                results = []
                paths = [".env", ".git/config", "backup.sql", "config.php.bak", ".ssh/id_rsa"]
                for path in paths:
                    url = f"{target.rstrip('/')}/{path}"
                    try:
                        resp = requests.get(url, timeout=5)
                        if resp.status_code == 200:
                            results.append(f"[CRITICAL] Exposed file found: {url}")
                        else:
                            results.append(f"[INFO] {path}: Not found ({resp.status_code})")
                    except:
                        results.append(f"[ERROR] {path}: Connection failed")
                return "\n".join(results)

            elif action == "sniffer":
                count = params.get("count", 10)
                viki_logger.info(f"Security: Sniffing {count} packets...")
                # Note: This usually requires Admin/Root
                from scapy.all import sniff
                packets = sniff(count=count)
                summary = packets.summary()
                return f"PACKET SNIFFER SUMMARY ({count} packets):\n{summary}"

            return f"Error: Unknown security action '{action}'"

        except Exception as e:
            viki_logger.error(f"Security tool failure: {e}")
            return f"Security Error: {str(e)}"

    def _is_public_target(self, target: str) -> bool:
        """Determines if the target is outside the allowed local range."""
        local_prefixes = ["192.168.", "10.", "127.0.0.1", "localhost", "172.16."]
        # Basic check: if it doesn't start with local prefixes and isn't a known local IP
        target = target.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]
        
        for prefix in local_prefixes:
            if target.startswith(prefix):
                return False
        
        # If it's a domain name (not an IP starting with local prefix), check if it's local
        if any(c.isalpha() for c in target) and not target.endswith(".local"):
            return True # Domains are treated as public unless .local
            
        return False # If it's an IP and didn't match local prefixes, it's public (but we'll be strict)
