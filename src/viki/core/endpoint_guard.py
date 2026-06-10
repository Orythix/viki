"""
Local endpoint guard: heuristic file-risk checks and optional OS AV CLI.

- Windows: Microsoft Defender (MpCmdRun.exe) when enabled in settings.
- Linux / macOS: optional ClamAV (clamscan or clamdscan on PATH) when enabled.
- Core heuristics and directory watching work on any OS where `watchdog` runs.

This complements real antivirus; it is not a full AV engine.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from viki.config.logger import viki_logger

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}

_DOUBLE_EXT = re.compile(
    r"\.[a-z0-9]{1,5}\.(exe|bat|cmd|scr|pif|com|vbs|js|jar|ps1|msi|dll|reg|sh|command|deb|rpm|dmg|pkg|run|bin|app)$",
    re.IGNORECASE,
)
_RANSOM_HINT = re.compile(
    r"(decrypt|restore.files|readme.?recover|how.?to.?restore|\.locked|\.encrypted)",
    re.IGNORECASE,
)
_HIGH_RISK_EXT = frozenset(
    {
        ".exe",
        ".scr",
        ".pif",
        ".bat",
        ".cmd",
        ".vbs",
        ".js",
        ".jar",
        ".ps1",
        ".msi",
        ".com",
        ".dll",
        ".sh",
        ".command",
        ".deb",
        ".rpm",
        ".dmg",
        ".pkg",
        ".run",
        ".bin",
        ".app",
    }
)


def assess_path_risk(path: str) -> Tuple[str, str]:
    """
    Return (severity, reason) for a filesystem path. severity in low|medium|high.
    """
    if not path or not isinstance(path, str):
        return "low", ""
    base = os.path.basename(path)
    lower = base.lower()

    if _RANSOM_HINT.search(base):
        return "high", "Filename matches common ransomware / recovery-note patterns"

    if _DOUBLE_EXT.search(lower):
        return "high", "Double extension (possible executable masquerade)"

    _, ext = os.path.splitext(lower)
    if ext in _HIGH_RISK_EXT:
        parent = os.path.basename(os.path.dirname(path)).lower()
        if parent in ("downloads", "temp", "tmp") or "download" in parent:
            return "medium", f"Executable/script type {ext} in a download-style folder"
        return "low", f"High-risk extension {ext}"

    return "low", ""


def severity_meets(minimum: str, actual: str) -> bool:
    return _SEVERITY_ORDER.get(actual, 0) >= _SEVERITY_ORDER.get(minimum, 1)


def find_mp_cmd_run() -> Optional[str]:
    if os.name != "nt":
        return None
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidate = os.path.join(pf, "Windows Defender", "MpCmdRun.exe")
    if os.path.isfile(candidate):
        return candidate
    return None


def scan_with_windows_defender(file_path: str, timeout_s: int = 120) -> str:
    """Run a Defender custom scan on one file (Windows only)."""
    mpcmd = find_mp_cmd_run()
    if not mpcmd:
        return "Windows Defender CLI (MpCmdRun.exe) not found."
    if not os.path.isfile(file_path):
        return f"Not a file: {file_path}"
    try:
        r = subprocess.run(
            [mpcmd, "-Scan", "-ScanType", "3", "-File", file_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or f"Defender finished (exit {r.returncode})."
    except subprocess.TimeoutExpired:
        return "Defender scan timed out."
    except OSError as e:
        return f"Defender scan failed: {e}"


def find_clamscan() -> Optional[str]:
    """First of clamdscan / clamscan on PATH (Linux, macOS, BSD)."""
    for name in ("clamdscan", "clamscan"):
        p = shutil.which(name)
        if p:
            return p
    return None


def scan_with_clamav(file_path: str, timeout_s: int = 180) -> str:
    """Run ClamAV on one file (POSIX). Prefer clamdscan if installed."""
    cli = find_clamscan()
    if not cli:
        return "ClamAV (clamscan or clamdscan) not found on PATH."
    if not os.path.isfile(file_path):
        return f"Not a file: {file_path}"
    try:
        if os.path.basename(cli).lower().startswith("clamdscan"):
            cmd = [cli, file_path]
        else:
            cmd = [cli, "--no-summary", file_path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        out = (r.stdout or "") + (r.stderr or "")
        return out.strip() or f"ClamAV finished (exit {r.returncode})."
    except subprocess.TimeoutExpired:
        return "ClamAV scan timed out."
    except OSError as e:
        return f"ClamAV scan failed: {e}"


def scan_file_with_best_os_cli(file_path: str, use_defender: bool, use_clamav: bool) -> str:
    """Windows: Defender if available. Else POSIX: ClamAV if enabled and available."""
    if os.name == "nt" and use_defender and find_mp_cmd_run():
        return scan_with_windows_defender(file_path)
    if os.name != "nt" and use_clamav and find_clamscan():
        return scan_with_clamav(file_path)
    if os.name == "nt":
        return "Windows Defender CLI not available for this path."
    if use_clamav:
        return "ClamAV not on PATH; install clamav and ensure clamscan or clamdscan is available."
    return "Set endpoint_guard.use_clamav_cli: true and install ClamAV for CLI scanning on this OS."


def candidate_download_directories() -> List[str]:
    """
    Resolved download folders: XDG (Linux), ~/Downloads, and workspace-adjacent common names.
    De-duplicated, only existing directories.
    """
    seen: set[str] = set()
    out: List[str] = []

    def add(raw: str) -> None:
        if not raw or not isinstance(raw, str):
            return
        try:
            ap = os.path.abspath(os.path.expanduser(raw.strip()))
            if ap in seen or not os.path.isdir(ap):
                return
            seen.add(ap)
            out.append(ap)
        except OSError:
            return

    xdg = (os.environ.get("XDG_DOWNLOAD_DIR") or "").strip()
    if xdg:
        add(xdg)

    try:
        ud = os.path.expanduser("~/.config/user-dirs.dirs")
        if os.path.isfile(ud):
            with open(ud, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line.startswith("XDG_DOWNLOAD_DIR="):
                        continue
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    val = val.replace("$HOME", os.path.expanduser("~"))
                    add(val)
                    break
    except OSError:
        pass

    add("~/Downloads")

    return out


class _GuardHandler(FileSystemEventHandler):
    def __init__(
        self,
        on_event: Callable[[str], None],
        debounce_s: float,
        ignore_prefixes: Tuple[str, ...],
    ):
        super().__init__()
        self._on_event = on_event
        self._debounce_s = debounce_s
        self._last: Dict[str, float] = {}
        self._ignore = ignore_prefixes

    def on_created(self, event):
        self._handle(event.src_path, event.is_directory)

    def on_moved(self, event):
        self._handle(event.dest_path, event.is_directory)

    def _handle(self, src_path: str, is_dir: bool):
        if is_dir:
            return
        low = src_path.replace("\\", "/").lower()
        for pref in self._ignore:
            if pref and low.startswith(pref):
                return
        now = time.time()
        if now - self._last.get(src_path, 0) < self._debounce_s:
            return
        self._last[src_path] = now
        self._on_event(src_path)


class EndpointGuardService:
    """
    Watches configured folders and scores new files; optionally runs Defender.
    """

    def __init__(self, controller: Any):
        self.controller = controller
        self._observer: Optional[Any] = None
        self._running = False

    def _cfg(self) -> Dict[str, Any]:
        raw = getattr(self.controller, "settings", {}) or {}
        eg = raw.get("endpoint_guard")
        return eg if isinstance(eg, dict) else {}

    def _default_watch_paths(self) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for dl in candidate_download_directories():
            if dl not in seen:
                seen.add(dl)
                out.append(dl)
        try:
            ws = (self.controller.settings.get("system") or {}).get("workspace_dir", "./workspace")
            w = os.path.abspath(os.path.expanduser(ws))
            if os.path.isdir(w) and w not in seen:
                seen.add(w)
                out.append(w)
        except OSError:
            pass
        return out

    def resolve_watch_paths(self) -> List[str]:
        cfg = self._cfg()
        paths = cfg.get("watch_paths")
        if isinstance(paths, list) and paths:
            resolved = []
            for p in paths:
                if not p or not isinstance(p, str):
                    continue
                ap = os.path.abspath(os.path.expanduser(p.strip()))
                if os.path.isdir(ap):
                    resolved.append(ap)
            return resolved
        return self._default_watch_paths()

    def start_watcher(self) -> None:
        if Observer is None:
            viki_logger.warning("endpoint_guard: watchdog package missing; watcher disabled.")
            return
        # Avoid background threads / FS hooks during pytest collection and tests.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        cfg = self._cfg()
        if not cfg.get("enabled"):
            return
        if getattr(self.controller, "low_resource_mode", False):
            viki_logger.info("endpoint_guard: low_resource_mode — watcher not started.")
            return
        if not cfg.get("auto_start_watcher", True):
            return
        if self._running:
            return

        paths = self.resolve_watch_paths()
        if not paths:
            viki_logger.warning("endpoint_guard: no watch paths resolved.")
            return

        min_sev = str(cfg.get("alert_on_severity", "medium")).lower()
        use_def = bool(cfg.get("use_windows_defender_cli", True))
        use_clam = bool(cfg.get("use_clamav_cli", False))
        debounce = float(cfg.get("debounce_seconds", 2.0))
        data_dir = os.path.abspath(
            (self.controller.settings.get("system") or {}).get("data_dir", "./data")
        )
        ignore_norm = tuple(
            x.replace("\\", "/").lower().rstrip("/")
            for x in (data_dir, getattr(self.controller, "DEFAULT_DATA_DIR", ""))
            if x
        )

        def sync_handle(src_path: str):
            sev, reason = assess_path_risk(src_path)
            if not severity_meets(min_sev, sev):
                return
            msg = f"endpoint_guard: [{sev}] {src_path} — {reason}"
            viki_logger.warning(msg)
            try:
                self.controller.learning.save_lesson(
                    trigger="ENDPOINT_GUARD_ALERT",
                    fact=msg,
                    source_task="endpoint_guard",
                )
            except Exception as e:
                viki_logger.debug("endpoint_guard lesson: %s", e)
            if sev == "high" and (
                (os.name == "nt" and use_def) or (os.name != "nt" and use_clam)
            ):
                report = scan_file_with_best_os_cli(src_path, use_def, use_clam)
                viki_logger.info("endpoint_guard AV scan: %s", report[:500])

        # Watchdog runs in a background thread; keep handling synchronous (no asyncio loop required).
        handler = _GuardHandler(sync_handle, debounce, ignore_norm)
        self._observer = Observer()
        for p in paths:
            try:
                self._observer.schedule(handler, p, recursive=False)
                viki_logger.info("endpoint_guard: watching %s", p)
            except OSError as e:
                viki_logger.warning("endpoint_guard: cannot watch %s: %s", p, e)
        self._observer.start()
        self._running = True

    def stop_watcher(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5.0)
            except Exception as e:
                viki_logger.debug("endpoint_guard stop: %s", e)
            self._observer = None
        self._running = False
