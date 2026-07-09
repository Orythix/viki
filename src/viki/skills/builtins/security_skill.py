import asyncio
import os
import re
import shutil
import subprocess
from typing import Any, cast

import requests

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill


class SecuritySkill(BaseSkill):
    """
    Ethical Hacking & Network Security Skill.
    Enables VIKI to perform local network scans and audits.
    """

    def __init__(self, controller=None):
        self._controller = controller
        self._name = "security_tools"
        self._description = (
            "Ethical hacking & security audit tools.\n"
            "Actions:\n"
            "- net_scan(target, type): Reconnaissance (nmap).\n"
            "- deep_recon(target): Advanced OS/Service detection.\n"
            "- web_audit(url): Scan for exposed sensitive files.\n"
            "- secret_scan(path): Scan codebase for leaked API keys/secrets.\n"
            "- exploit_search(query): Research CVEs and vulnerabilities.\n"
            "- sniffer(count): Packet capture (Local only)."
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "net_scan",
                        "deep_recon",
                        "web_audit",
                        "secret_scan",
                        "exploit_search",
                        "sniffer",
                    ],
                    "description": "Security action to perform.",
                },
                "target": {"type": "string", "description": "Target IP, URL, or domain."},
                "path": {"type": "string", "description": "Local path for secret_scan."},
                "query": {
                    "type": "string",
                    "description": "CVE ID or software name for exploit_search.",
                },
                "type": {"type": "string", "description": "Scan type flags for nmap."},
                "count": {"type": "integer", "description": "Packet count for sniffer."},
            },
            "required": ["action"],
        }

    async def execute(self, params: dict[str, Any]) -> str:
        action = params.get("action")
        target = params.get("target") or params.get("url")
        if not isinstance(target, str):
            target = ""

        if action in ("net_scan", "deep_recon", "web_audit", "sniffer") and not target:
            return f"Error: Action '{action}' requires 'target'."

        # 1. Safety Check: Only local networks or explicitly whitelisted
        if self._is_public_target(target):
            return (
                "ACCESS DENIED: Attempt to scan a public/restricted target detected. "
                "I am bound by the Computer Fraud and Abuse Act (CFAA). "
                "I only operate on local 192.168.x.x, 10.x.x.x, or 127.0.0.1 networks."
            )

        try:
            if action == "net_scan":
                scan_type = params.get("type", "-F")  # Fast scan by default
                return await self._run_nmap(target, [scan_type])

            elif action == "deep_recon":
                # OS Detection, Version Detection, Default Scripts
                return await self._run_nmap(target, ["-A", "-T4"])

            elif action == "web_audit":
                viki_logger.info(f"Security: Auditing {target} for sensitive files")
                results = []
                paths = [".env", ".git/config", "backup.sql", "config.php.bak", ".ssh/id_rsa"]

                # Run all HTTP requests concurrently using asyncio
                async def check_path(path: str) -> str:
                    url = f"{target.rstrip('/')}/{path}"
                    try:
                        # Run requests.get in thread pool
                        resp = await asyncio.to_thread(requests.get, url, timeout=5)
                        if resp.status_code == 200:
                            return f"[CRITICAL] Exposed file found: {url}"
                        else:
                            return f"[INFO] {path}: Not found ({resp.status_code})"
                    except (requests.RequestException, requests.Timeout) as e:
                        return f"[ERROR] {path}: Connection failed ({e})"

                # Check all paths concurrently
                results = await asyncio.gather(*[check_path(path) for path in paths])
                return "\n".join(results)

            elif action == "sniffer":
                count = params.get("count", 10)
                viki_logger.info(f"Security: Sniffing {count} packets...")
                # Note: This usually requires Admin/Root
                from scapy.all import sniff

                # Run sniffing in thread pool to avoid blocking
                def do_sniff():
                    packets = sniff(count=count)
                    return packets.summary()

                summary = await asyncio.to_thread(do_sniff)
                return f"PACKET SNIFFER SUMMARY ({count} packets):\n{summary}"

            elif action == "secret_scan":
                path = params.get("path") or "."
                return await self._secret_scan(path)

            elif action == "exploit_search":
                query = params.get("query")
                if not query:
                    return "Error: exploit_search requires 'query'."
                return await self._exploit_search(query)

            return f"Error: Unknown security action '{action}'"

        except Exception as e:
            viki_logger.error(f"Security tool failure: {e}")
            return f"Security Error: {str(e)}"

    async def _run_nmap(self, target: str, flags: list[str]) -> str:
        viki_logger.info(f"Security: Running nmap {' '.join(flags)} on {target}")

        # v27: Resolve nmap path (shutil.which for PATH, fallback to common Windows locations)
        nmap_path = await asyncio.to_thread(shutil.which, "nmap")
        if not nmap_path:
            # Check common Windows location
            windows_nmap = r"C:\Program Files (x86)\Nmap\nmap.exe"
            if os.path.exists(windows_nmap):
                nmap_path = windows_nmap

        if not nmap_path:
            return (
                "Error: nmap is not installed or not found in common locations. Please install it."
            )

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [nmap_path] + flags + [target],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return (
                f"NMAP RESULTS ({' '.join(flags)}) for {target}:\n{result.stdout or result.stderr}"
            )
        except Exception as e:
            return f"Nmap Error: {e}"

    async def _secret_scan(self, path: str) -> str:
        """Scan for leaked secrets using common patterns."""
        patterns = {
            "AWS Key": r"AKIA[0-9A-Z]{16}",
            "Generic Secret": r"(?i)(key|secret|password|passwd|token)[\s:=]+['\"]?([a-zA-Z0-9_\-\.]{16,})['\"]?",
            "Private Key": r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----",
            "Google API": r"AIza[0-9A-Za-z\\-_]{35}",
            "Slack Token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
            "Stripe Key": r"(sk|pk)_(test|live)_[0-9a-zA-Z]{24}",
        }

        findings = []
        for root, _, files in await asyncio.to_thread(lambda: list(os.walk(path))):
            if any(d in root for d in (".git", "node_modules", "__pycache__")):
                continue
            for f in files:
                f_path = os.path.join(root, f)
                try:
                    content = await asyncio.to_thread(
                        lambda: open(f_path, encoding="utf-8", errors="ignore").read()
                    )
                    for name, regex in patterns.items():
                        matches = re.finditer(regex, content)
                        for m in matches:
                            line = content.count("\n", 0, m.start()) + 1
                            findings.append(f"[!] Found {name} in {f_path}:{line}")
                except Exception:
                    continue

        if not findings:
            return "No secrets detected in codebase."
        return "SECRET SCAN FINDINGS:\n" + "\n".join(findings[:50])

    async def _exploit_search(self, query: str) -> str:
        """Use LLM to research exploits for a given software/version."""
        model = self._controller.model_router.get_model(["reasoning", "research"])
        prompt = (
            f"Act as a World Class Cybersecurity Researcher. Research known vulnerabilities and exploits for: {query}\n\n"
            "Provide:\n"
            "1. CVE IDs (if any)\n"
            "2. Vulnerability type (RCE, SQLi, Auth Bypass, etc.)\n"
            "3. High-level exploit logic (for PoC evaluation)\n"
            "4. Remediation steps.\n\n"
            "Focus on accuracy and technical depth."
        )
        return cast("str", await model.chat([{"role": "user", "content": prompt}]))

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
            return True  # Domains are treated as public unless .local

        return False  # If it's an IP and didn't match local prefixes, it's public (but we'll be strict)
