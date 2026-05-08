from __future__ import annotations

import os
from typing import Any, Dict, List

from viki.config.logger import viki_logger
from viki.skills.base import BaseSkill
from viki.core.endpoint_guard import (
    assess_path_risk,
    find_clamscan,
    find_mp_cmd_run,
    scan_file_with_best_os_cli,
    severity_meets,
)


class EndpointGuardSkill(BaseSkill):
    """
    Local endpoint guard: heuristic risk scoring, directory sweep, optional AV CLI (Defender on Windows, ClamAV on POSIX).
    Complements OS antivirus; does not replace it.
    """

    def __init__(self, controller=None):
        self.controller = controller

    @property
    def name(self) -> str:
        return "endpoint_guard"

    @property
    def description(self) -> str:
        return (
            "Local security guard: assess_file(path), scan_directory(path), defender_scan(path), "
            "defender_status, start_watcher, stop_watcher. Cross-platform heuristics; "
            "defender_scan uses Defender (Windows) or ClamAV when use_clamav_cli is on."
        )

    @property
    def safety_tier(self) -> str:
        return "safe"

    @property
    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "assess_file",
                        "scan_directory",
                        "defender_scan",
                        "defender_status",
                        "start_watcher",
                        "stop_watcher",
                    ],
                    "description": "Guard action",
                },
                "path": {"type": "string", "description": "File or directory path"},
                "max_files": {
                    "type": "integer",
                    "description": "Max files for scan_directory (default 400)",
                },
            },
            "required": ["action"],
        }

    @property
    def triggers(self) -> List[str]:
        return [
            "malware",
            "virus",
            "antivirus",
            "defender",
            "suspicious file",
            "download safe",
            "scan this file",
            "endpoint guard",
        ]

    async def execute(self, params: Dict[str, Any]) -> str:
        action = (params.get("action") or "").strip().lower()
        if not action:
            return "endpoint_guard: 'action' is required."

        svc = getattr(self.controller, "endpoint_guard", None) if self.controller else None

        if action == "defender_status":
            lines: List[str] = []
            mpcmd = find_mp_cmd_run()
            if mpcmd:
                lines.append(f"Windows Defender CLI: {mpcmd}")
            clam = find_clamscan()
            if clam:
                lines.append(f"ClamAV CLI: {clam}")
            if lines:
                return "\n".join(lines)
            return (
                "No Defender or ClamAV CLI found. Heuristic watching still works on all OSes; "
                "on Linux/macOS install ClamAV and set endpoint_guard.use_clamav_cli: true for scans."
            )

        if action == "defender_scan":
            path = params.get("path") or ""
            if not path or not os.path.isfile(os.path.expanduser(path)):
                return "defender_scan: provide a valid file path."
            ap = os.path.abspath(os.path.expanduser(path))
            eg: Dict[str, Any] = {}
            if self.controller and getattr(self.controller, "settings", None):
                raw = self.controller.settings.get("endpoint_guard") or {}
                eg = raw if isinstance(raw, dict) else {}
            use_def = bool(eg.get("use_windows_defender_cli", True))
            use_clam = bool(eg.get("use_clamav_cli", False))
            return scan_file_with_best_os_cli(ap, use_def, use_clam)

        if action == "assess_file":
            path = params.get("path") or ""
            if not path:
                return "assess_file: 'path' is required."
            ap = os.path.abspath(os.path.expanduser(path))
            if not os.path.isfile(ap):
                return f"assess_file: not a file: {ap}"
            sev, reason = assess_path_risk(ap)
            return f"Risk: {sev}. {reason or 'No heuristic flags.'} Path: {ap}"

        if action == "scan_directory":
            raw = params.get("path") or ""
            if not raw:
                return "scan_directory: 'path' is required."
            root = os.path.abspath(os.path.expanduser(raw))
            if not os.path.isdir(root):
                return f"scan_directory: not a directory: {root}"
            max_files = max(10, min(int(params.get("max_files") or 400), 5000))
            cfg_min = "medium"
            if self.controller and getattr(self.controller, "settings", None):
                eg = (self.controller.settings.get("endpoint_guard") or {})
                if isinstance(eg, dict) and eg.get("alert_on_severity"):
                    cfg_min = str(eg["alert_on_severity"]).lower()

            findings: List[str] = []
            count = 0
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if count >= max_files:
                        break
                    fp = os.path.join(dirpath, fn)
                    count += 1
                    sev, reason = assess_path_risk(fp)
                    if severity_meets(cfg_min, sev) and sev != "low":
                        findings.append(f"[{sev}] {fp}: {reason}")
                if count >= max_files:
                    break
            if not findings:
                return f"scan_directory: scanned {count} files under {root}; no paths matched threshold '{cfg_min}'."
            return f"scan_directory: {len(findings)} finding(s) (threshold {cfg_min}, cap {max_files} files):\n" + "\n".join(
                findings[:50]
            ) + (f"\n... and {len(findings) - 50} more" if len(findings) > 50 else "")

        if action == "start_watcher":
            if not svc or not self.controller:
                return "endpoint_guard: controller not available."
            svc.stop_watcher()
            svc.start_watcher()
            return "endpoint_guard: watcher (re)started for configured paths."

        if action == "stop_watcher":
            if not svc:
                return "endpoint_guard: service not available."
            svc.stop_watcher()
            return "endpoint_guard: watcher stopped."

        return f"endpoint_guard: unknown action '{action}'."
