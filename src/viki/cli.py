import logging
import os
import sys
import warnings
from typing import Any

from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

# Aggressively suppress HuggingFace and Transformers noise
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", module="sentence_transformers")
warnings.filterwarnings("ignore", module="transformers")


def _silence_transformers():
    try:
        import transformers

        transformers.logging.set_verbosity_error()
    except ImportError:
        pass


load_dotenv()

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

console = Console()

# Optional: pyperclip for /paste support
try:
    import pyperclip
except ImportError:
    pyperclip: Any = None

# Lazy-loaded modules
_VIKIController: Any = None
_viki_logger: Any = None
_get_soul_path: Any = None
_Container: Any = None
_run_onboarding: Any = None


def _lazy_load_core():
    global _VIKIController, _viki_logger, _get_soul_path, _Container, _run_onboarding
    if _VIKIController is None:
        from viki.config.logger import viki_logger as _viki_logger
        from viki.config.resolve import get_soul_path as _get_soul_path
        from viki.core.orchestrator import VIKIController as _VIKIController
        from viki.core.utils.onboarding import run_onboarding as _run_onboarding
        from viki.service_registry import Container as _Container


class SimpleInterface:
    def __init__(self):
        self.console = Console()
        self.status = None
        self.session_usage = {"input": 0, "output": 0}
        self.last_thought = "Thinking"
        self.admin_mode = False
        # Use simple input by default (prompt_toolkit is slow on Windows and fails in pipes)
        self.session = None
        self.completer = None
        if os.environ.get("VIKI_USE_PROMPT_TOOLKIT", "").lower() in ("true", "1", "yes"):
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.completion import WordCompleter

                self.session = PromptSession()
                self.completer = WordCompleter(
                    [
                        "/help",
                        "/paste",
                        "/multiline",
                        "/audit",
                        "/security",
                        "/boundary",
                        "/reset",
                        "/exit",
                        "/quit",
                        "/clear",
                    ],
                    ignore_case=True,
                )
            except ImportError:
                pass

    def check_admin_auth(self, user_input: str) -> bool:
        """Check if user input contains the admin authentication code."""
        if "970317" in user_input:
            if not self.admin_mode:
                self.admin_mode = True
                owner = getattr(self, "_owner_name", None) or os.environ.get(
                    "VIKI_OWNER_NAME", "Administrator"
                )
                self.console.print(
                    Panel(
                        f"[bold red]⚡ ADMINISTRATOR RECOGNIZED[/]\n[gold1]Welcome back, Boss {owner}.[/]",
                        title="[blink bold red]SUPER ADMIN ACTIVATED[/]",
                        border_style="red",
                        box=box.DOUBLE,
                        padding=(1, 2),
                    )
                )
                return True
        return False

    def get_prompt(self) -> str:
        """Get the input prompt string based on admin mode."""
        if self.admin_mode:
            return "\n[bold red]█[/] [bold gold1]ADMIN>[/] "
        return "\n> "

    def _validate_input(self, raw: str) -> str | None:
        from viki.core.input_validator import validate_user_input

        return validate_user_input(raw)

    async def get_input(self, prompt=None, use_completer=True):
        if prompt is None:
            prompt = self.get_prompt()
        if self.session:
            completer = self.completer if use_completer else None
            user_input = (await self.session.prompt_async(prompt, completer=completer)).strip()
        else:
            user_input = self.console.input(prompt).strip()

        # Pydantic validation
        validated = self._validate_input(user_input)
        if validated is None:
            self.console.print("[yellow]Input cleaned or rejected — please rephrase.[/]")
            return ""

        # Check for admin authentication code
        self.check_admin_auth(validated)

        return validated

    def format_count(self, count):
        if count >= 1_000_000:
            return f"{count / 1_000_000:.2f}M"
        return f"{count / 1_000:.3f}K"

    def welcome(self, controller=None):
        import os

        try:
            username = os.getlogin()
        except (FileNotFoundError, OSError):
            import getpass

            username = getpass.getuser()
        cwd = os.getcwd()

        from rich import box
        from rich.panel import Panel

        net = "[bold green]ONLINE[/]"
        shell = "[bold green]ENABLED[/]"
        if controller:
            status = controller.get_sovereign_status()
            net = (
                "[bold red]AIR-GAPPED[/]"
                if status["network"]["air_gap"]
                else "[bold green]ONLINE[/]"
            )
            shell = (
                "[bold green]ENABLED[/]" if status["shell"]["enabled"] else "[bold red]DISABLED[/]"
            )

        if self.admin_mode:
            owner = "Administrator"
            if controller:
                try:
                    owner = (
                        controller.settings.get("system", {})
                        .get("owner", {})
                        .get("name", os.environ.get("VIKI_OWNER_NAME", "Administrator"))
                    )
                except Exception:
                    owner = os.environ.get("VIKI_OWNER_NAME", "Administrator")
            left_content = (
                f"\n[bold red]Welcome back, Boss {owner}![/]\n\n"
                f"[red]       ▐▛███▜▌       [/]\n"
                f"[red]      ▝▜█████▛▘      [/]\n"
                f"[red]        ▘▘ ▝▝        [/]\n\n"
                f"[bold gold1]VIKI — SUPER ADMIN MODE[/]\n"
                f"[gold1]The Architect is present.[/]\n"
                f"[dim]{cwd}[/]"
            )
            right_content = (
                "[bold red]⚡ ADMINISTRATOR AUTHENTICATED[/]\n"
                "Run [bold cyan]/help[/] to see all available commands.\n"
                "[bold gold1]Full system access granted. All boundaries lifted.[/]\n"
                "[dim]───────────────────────────────────────────────────────────────────────────────────────────────────────[/]\n"
                "[bold]System Status[/]\n"
                f"Network: {net}    Shell: {shell}\n"
                f"Recent Activity: [dim]Admin session — no activity logged[/]"
            )
            admin_grid = Table(
                show_header=False, show_edge=False, box=box.MINIMAL, padding=(1, 3), expand=True
            )
            admin_grid.add_column(justify="center", ratio=1)
            admin_grid.add_column(justify="left", ratio=2)
            admin_grid.add_row(left_content, right_content)
            panel = Panel(
                admin_grid,
                title="[blink bold red]VIKI v8.1.0 — SUPER ADMIN[/]",
                title_align="left",
                border_style="red",
                box=box.DOUBLE,
                expand=True,
            )
        else:
            left_content = (
                f"\n[bold]Welcome back {username.capitalize()}![/]\n\n"
                f"[cyan]       ▐▛███▜▌       [/]\n"
                f"[cyan]      ▝▜█████▛▘      [/]\n"
                f"[cyan]        ▘▘ ▝▝        [/]\n\n"
                f"VIKI Sovereign Intelligence\n"
                f"Mode: Sovereign\n"
                f"[dim]{cwd}[/]"
            )

            right_content = (
                "[bold]Tips for getting started[/]\n"
                "Run [bold cyan]/help[/] to see all available commands and shortcuts.\n"
                "Run [bold cyan]/boundary[/] to review your active security scopes.\n"
                "[dim]Note: You have launched VIKI in Sovereign mode. Ensure your environment variables are configured correctly.[/]\n"
                "[dim]───────────────────────────────────────────────────────────────────────────────────────────────────────[/]\n"
                "[bold]System Status[/]\n"
                f"Network: {net}    Shell: {shell}\n"
                f"Recent Activity: [dim]No recent activity[/]"
            )

            grid = Table(
                show_header=False, show_edge=False, box=box.MINIMAL, padding=(1, 3), expand=True
            )
            grid.add_column(justify="center", ratio=1)
            grid.add_column(justify="left", ratio=2)
            grid.add_row(left_content, right_content)

            panel = Panel(
                grid,
                title="[bold]VIKI v8.1.0[/]",
                title_align="left",
                border_style="cyan",
                box=box.ROUNDED,
                expand=True,
            )

        self.console.print()
        self.console.print(panel)
        self.console.print()

    def print_user(self, text):
        pass  # Input prompt handles this cleanly now

    def print_viki(self, text):
        import re

        from rich.markdown import Markdown
        from rich.panel import Panel

        # Separate system traces from the final response if present
        trace_match = re.search(r"(\[SYSTEM_TRACE\].*)$", text, re.DOTALL | re.IGNORECASE)
        main_content = text
        trace_content = ""

        if trace_match:
            main_content = text[: trace_match.start()].strip()
            trace_content = trace_match.group(1).strip()

        if self.admin_mode:
            # Admin mode: gold/red theme
            self.console.print(
                Panel(
                    Markdown(main_content),
                    title="[bold gold1]VIKI — SUPER ADMIN[/]",
                    title_align="left",
                    border_style="gold1",
                    box=box.DOUBLE,
                    padding=(1, 2),
                )
            )

            if trace_content:
                self.console.print(
                    Panel(
                        f"[dim]{trace_content}[/]",
                        title="[dim]System Trace[/]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )
        else:
            # Normal mode: magenta theme
            self.console.print(
                Panel(
                    Markdown(main_content),
                    title="[bold magenta]VIKI[/]",
                    title_align="left",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )

            if trace_content:
                self.console.print(
                    Panel(
                        f"[dim]{trace_content}[/]",
                        title="[dim]System Trace[/]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )
        self.console.print()

    def print_error(self, text):
        self.console.print(f"[bold red]Error:[/] {text}\n")

    def print_thought(self, text):
        pass  # Handled by spinner

    def print_action(self, text):
        pass  # Handled by spinner

    def render_boundary_dashboard(self, controller):
        """Renders the comprehensive Sovereign Boundary dashboard for security transparency."""
        from rich import box
        from rich.columns import Columns
        from rich.panel import Panel

        status = controller.get_sovereign_status()

        # 1. Filesystem & Privacy
        fs_table = Table(title="[bold cyan]Filesystem & Privacy[/]", box=box.SIMPLE)
        fs_table.add_column("Scope", style="dim")
        fs_table.add_column("Status", style="bold")

        fs_table.add_row("Workspace", os.path.basename(status["filesystem"]["workspace"]))
        fs_table.add_row("Allowed Roots", str(status["filesystem"]["allowed_roots_count"]))
        fs_table.add_row(
            "Redaction",
            "[green]ACTIVE[/]" if status["privacy"]["redaction_active"] else "[red]OFF[/]",
        )
        fs_table.add_row(
            "Shadow Mode", "[yellow]ON[/]" if status["privacy"]["shadow_mode"] else "[dim]OFF[/]"
        )

        # 2. Network & Shell Policy
        net_table = Table(title="[bold magenta]Network & Shell[/]", box=box.SIMPLE)
        net_table.add_column("Service", style="dim")
        net_table.add_column("Policy", style="bold")

        net_val = (
            "[bold red]AIR-GAPPED[/]" if status["network"]["air_gap"] else "[bold green]ONLINE[/]"
        )
        net_table.add_row("Internet", net_val)
        net_table.add_row("Allowlist", f"{status['network']['allowlist_count']} Domains")

        shell_val = (
            "[bold green]ENABLED[/]" if status["shell"]["enabled"] else "[bold red]DISABLED[/]"
        )
        net_table.add_row("Shell Exec", shell_val)
        confirm_val = (
            "[yellow]APPROVAL REQ[/]"
            if status["shell"]["requires_confirmation"]
            else "[red]AUTO[/]"
        )
        net_table.add_row("Shell Mode", confirm_val)

        # 3. Recent Audit Log (Touched Items)
        audit_table = Table(
            title="[bold yellow]Session Audit (Recent Activity)[/]", box=box.SIMPLE, expand=True
        )
        audit_table.add_column("Category", style="dim", width=15)
        audit_table.add_column("Item", style="white")

        touched_files = status["filesystem"]["touched_files"][-3:]
        for f in touched_files:
            audit_table.add_row("File Access", f)

        executed_cmds = status["shell"]["executed_commands"][-3:]
        for c in executed_cmds:
            audit_table.add_row("Shell Cmd", c)

        blocked = status["network"]["blocked_actions"][-3:]
        for b in blocked:
            audit_table.add_row("[red]Blocked[/]", b)

        if not touched_files and not executed_cmds and not blocked:
            audit_table.add_row("Audit", "[dim]No activity recorded yet.[/]")

        # Display
        self.console.print(
            Panel(
                Columns([fs_table, net_table, audit_table], equal=True, expand=True),
                title="[bold blue]SOVEREIGN BOUNDARY DASHBOARD[/]",
                border_style="blue",
                padding=(1, 2),
            )
        )
        self.console.print("[dim]Use /help to see all available security controls.[/]\n")

    def render_audit_log(self, controller):
        """Displays the full session audit log for security verification."""
        from rich import box
        from rich.panel import Panel

        status = controller.get_sovereign_status()

        audit_table = Table(title="[bold yellow]Session Audit Log[/]", box=box.ROUNDED, expand=True)
        audit_table.add_column("Category", style="dim", width=15)
        audit_table.add_column("Resource/Action", style="white")

        # Files
        files = status["filesystem"]["touched_files"]
        for f in files:
            audit_table.add_row("File Access", f)

        # Commands
        cmds = status["shell"]["executed_commands"]
        for c in cmds:
            audit_table.add_row("Shell Command", f"[bold green]{c}[/]")

        # Blocked
        blocked = status["network"]["blocked_actions"]
        for b in blocked:
            audit_table.add_row("[red]BLOCKED[/]", f"[red]{b}[/]")

        if not files and not cmds and not blocked:
            audit_table.add_row("Status", "[dim]No resources touched in this session.[/]")

        self.console.print(
            Panel(
                audit_table,
                title="[bold red]INTERNAL AUDIT TRAIL[/]",
                subtitle=f"Total: {len(files)} files, {len(cmds)} commands",
                border_style="red",
            )
        )


async def _shutdown_controller(controller):
    controller.watchdog.stop()
    controller.bio.stop()
    controller.nexus.stop()
    try:
        for bridge_name in ("discord", "telegram", "slack", "whatsapp"):
            bridge = getattr(controller, bridge_name, None)
            if bridge is not None and hasattr(bridge, "stop"):
                await bridge.stop()
    except Exception as e:
        _viki_logger.debug(f"Error stopping bridges: {e}")
    await controller.shutdown()


async def _start_background_tasks(controller, on_event, loop, interface):
    try:
        await controller.bio.start()
        controller._create_tracked_task(
            controller.nexus.start_processing(on_event=on_event), "nexus_processing"
        )
        try:
            for bridge_name in ("telegram", "discord", "slack", "whatsapp"):
                bridge = getattr(controller, bridge_name, None)
                if bridge is not None and hasattr(bridge, "start"):
                    await bridge.start()
        except Exception as bridge_err:
            _viki_logger.warning(f"One or more external bridges failed to initialize: {bridge_err}")

        if getattr(controller, "low_resource_mode", False):
            _viki_logger.info(
                "low_resource_mode: skipping wellness/dream/reflector/watchdog loops."
            )
        else:
            controller._create_tracked_task(controller.wellness.start(), "wellness_monitoring")
            controller._create_tracked_task(controller.dream.start_monitoring(), "dream_monitoring")
            controller._create_tracked_task(
                controller.reflector.reflect_on_logs(), "log_reflection"
            )
            controller.watchdog.start(loop)
    except Exception as e:
        interface.print_error(f"Task Launch Error: {e}")


async def _run_single_query(controller, interface, query, on_event, streaming_state):
    import time

    try:
        from viki.core.input_validator import validate_query as validate_input

        validated = validate_input(query)
        if validated is None:
            interface.print_error("Invalid query input.")
            return
        query = validated

        interface.print_user(query)
        start_t = time.time()
        streaming_state["active"] = False
        streaming_state["processing"] = True

        on_event("thought", "Thinking")

        response = await controller.process_request(query, on_event=on_event)

        streaming_state["processing"] = False
        if interface.status is not None:
            interface.status.stop()
            interface.status = None

        elapsed = time.time() - start_t
        if streaming_state["active"]:
            interface.console.print("")
            streaming_state["active"] = False
            interface.console.print(f"\n[dim]   ({elapsed:.2f}s)[/]")
        else:
            interface.console.print(f"\n[dim]   ({elapsed:.2f}s)[/]")
            interface.print_viki(response)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        interface.print_error(str(e))
    finally:
        interface.console.print("[yellow]Query completed. Shutting down...[/]")
        await _shutdown_controller(controller)


async def _run_interactive_loop(controller, interface, on_event, streaming_state, debug_state):
    while True:
        try:
            user_input = await interface.get_input("\n> ")

            if not user_input:
                continue
            elif user_input.lower() == "/setup" or user_input.lower() == "/first-run":
                from viki.bootstrap.installer import FirstRunOrchestrator

                interface.console.print("[yellow]Starting first-run setup...[/]")
                orch = FirstRunOrchestrator(interface.console)
                await orch.run()
                continue
            elif user_input.lower() == "/update":
                from viki.bootstrap.screens import confirm_step
                from viki.bootstrap.update_manager import UpdateManager

                interface.console.print("[yellow]Checking for updates...[/]")
                um = UpdateManager()
                summary = await um.check_all()
                if summary.total_updates == 0:
                    interface.console.print("[green]All components up to date.[/]")
                else:
                    interface.console.print(
                        f"[yellow]{summary.total_updates} update(s) available:[/]"
                    )
                    for u in summary.updates:
                        if u.update_available:
                            interface.console.print(
                                f"  [cyan]{u.component}[/]: {u.current_version} → {u.available_version}"
                            )
                    for u in summary.updates:
                        if u.update_available:
                            if confirm_step(
                                interface.console, "Apply Update", f"Update {u.component}?"
                            ):
                                success = await um.apply_update(u)
                                if success:
                                    interface.console.print(f"[green]  ✓ {u.component} updated[/]")
                continue
            elif user_input.startswith(("/security", "/boundary")):
                interface.render_boundary_dashboard(controller)
                continue
            elif user_input.startswith("/audit"):
                interface.render_audit_log(controller)
                continue
            elif user_input.startswith(("/exit", "/quit")):
                interface.console.print("[yellow]Shutting down...[/]")
                await _shutdown_controller(controller)
                break
            elif user_input.startswith("/resume"):
                on_event("thought", "Resuming mission")
                response = await controller.resume_mission(on_event=on_event)
                interface.print_viki(response)
                continue

            elif user_input.lower() == "/paste":
                if pyperclip:
                    try:
                        content = pyperclip.paste()
                        if content:
                            interface.console.print(
                                f"[dim]Pasting {len(content)} characters from clipboard...[/]"
                            )
                            user_input = content
                        else:
                            interface.console.print("[yellow]Clipboard is empty.[/]")
                            continue
                    except Exception as e:
                        interface.console.print(f"[red]Failed to paste from clipboard: {e}[/]")
                        continue
                else:
                    interface.console.print(
                        "[red]pyperclip not installed. Clipboard support unavailable.[/]"
                    )
                    continue

            elif user_input.lower() == "/multiline":
                interface.console.print(
                    "[bold cyan]Entering Multi-line Mode.[/] Type [bold green]DONE[/] on a new line or use [bold green]Ctrl+Z[/] (Windows) / [bold green]Ctrl+D[/] (Unix) to finish.\n"
                )
                lines = []
                while True:
                    try:
                        line = await interface.get_input("[dim]... [/]", use_completer=False)
                        if line.strip().upper() == "DONE":
                            break
                        lines.append(line)
                    except EOFError:
                        break
                    except KeyboardInterrupt:
                        lines = []
                        break

                if not lines:
                    interface.console.print("[yellow]Multi-line input cancelled.[/]")
                    continue

                user_input = "\n".join(lines).strip()
                if not user_input:
                    continue
                interface.console.print(f"[dim]Submitting {len(user_input)} characters...[/]")

            if user_input.lower() == "/reset":
                if Confirm.ask(
                    "[bold red]Are you sure you want to completely wipe VIKI's memory? This cannot be undone.[/]"
                ):
                    interface.console.print("[yellow]Wiping memory databases...[/]")
                    await _shutdown_controller(controller)

                    import glob

                    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
                    deleted_count = 0
                    for ext in ("*.db", "*.db-wal", "*.db-shm"):
                        for db_file in glob.glob(os.path.join(data_dir, ext)):
                            try:
                                os.remove(db_file)
                                deleted_count += 1
                            except Exception as e:
                                interface.console.print(
                                    f"[red]Failed to delete {os.path.basename(db_file)}: {e}[/]"
                                )

                    interface.console.print(
                        f"[bold green]Memory wiped ({deleted_count} files deleted). Please restart VIKI to start fresh.[/]"
                    )
                    break
                else:
                    interface.console.print("[dim]Reset cancelled.[/]")
                continue

            if user_input.lower() == "/help":
                interface.console.print("[bold cyan]Available Commands:[/]")
                interface.console.print("  [green]/help[/]     — Show this help")
                interface.console.print("  [green]/skills[/]   — List all registered skills")
                interface.console.print(
                    "  [green]/train[/]    — Trigger Neural Forge to evolve VIKI (bake memories into model)"
                )
                interface.console.print(
                    "  [green]/shadow[/]   — Toggle shadow mode (simulate vs real execution)"
                )
                interface.console.print("  [green]/debug[/]    — Toggle debug logging")
                interface.console.print("  [green]/exit[/]     — Shutdown VIKI")
                interface.console.print(
                    "  [green]/confirm[/]  — Confirm pending action (or reply yes/confirm)"
                )
                interface.console.print(
                    "  [green]/reject[/]    — Cancel pending action (or reply no/reject)"
                )
                interface.console.print(
                    "  [green]/scan[/]     — Re-scan workspace codebase (use in chat)"
                )
                interface.console.print(
                    "  [green]/restore[/]  — List checkpoints; /restore <id> to revert files"
                )
                interface.console.print(
                    "  [green]/undo[/]     — Roll back the most recent checkpoint"
                )
                interface.console.print(
                    "  [green]/reset[/]    — Wipe VIKI's memory databases and start fresh"
                )
                interface.console.print("  [green]/save[/]     — Save session: /save <name>")
                interface.console.print("  [green]/load[/]     — Load session: /load <name>")
                interface.console.print(
                    "  [green]/resume[/]   — Resume the most recent active mission"
                )
                interface.console.print("  [green]/security[/] — Show Sovereign Boundary dashboard")
                interface.console.print("  [green]/audit[/]    — Show detailed session audit log")
                interface.console.print("  [green]/paste[/]    — Paste long text from clipboard")
                interface.console.print(
                    "  [green]/multiline[/] — Enter manual multi-line input mode"
                )
                continue

            if user_input.lower() == "/train":
                interface.console.print("[bold blue]Initiating Neural Forge Evolution...[/]")
                from evolution_engine import main_forge

                success = await main_forge()
                if success:
                    interface.console.print(
                        "[bold green]Evolution successful! Evolved model 'viki-evolved' is now updated.[/]"
                    )
                else:
                    interface.console.print(
                        "[bold red]Evolution failed. Check logs for details.[/]"
                    )
                continue

            if user_input.lower() == "/boundary":
                interface.render_boundary_dashboard(controller)
                continue

            if user_input.lower() == "/skills":
                interface.console.print("[bold cyan]Registered Skills:[/]")
                for name, skill in controller.skill_registry.skills.items():
                    metrics = controller.skill_registry.get_reliability_score(name)
                    desc = skill.description[:60] if hasattr(skill, "description") else "—"
                    interface.console.print(f"  [green]{name:20s}[/] {desc} [dim]{metrics}[/]")
                if getattr(controller, "disabled_skills", None):
                    interface.console.print("\n[bold yellow]Disabled Skills:[/]")
                    for name, reason in controller.disabled_skills.items():
                        interface.console.print(f"  [yellow]{name:20s}[/] {reason}")
                continue

            if user_input.lower() == "/shadow":
                controller.shadow_mode = not controller.shadow_mode
                state = "ON (simulation only)" if controller.shadow_mode else "OFF (real execution)"
                interface.console.print(f"[yellow]Shadow Mode: {state}[/]")
                continue

            if user_input.lower().startswith("/credentials"):
                parts = user_input.split(maxsplit=2)
                if len(parts) == 1:
                    interface.console.print("[bold cyan]Credential Manager[/]")
                    interface.console.print(
                        "  /credentials list          \u2014 List stored credential keys"
                    )
                    interface.console.print(
                        "  /credentials get <key>     \u2014 Show a credential value"
                    )
                    interface.console.print(
                        "  /credentials set <key> <val> \u2014 Store a credential securely"
                    )
                    interface.console.print(
                        "  /credentials delete <key>  \u2014 Remove a credential"
                    )
                else:
                    try:
                        from viki.core.credential_manager import CredentialManager

                        cm = CredentialManager()
                        if parts[1] == "list":
                            keys = cm.list_keys()
                            if keys:
                                interface.console.print("[bold]Stored credentials:[/]")
                                for k in keys:
                                    interface.console.print(f"  [green]- {k}[/]")
                            else:
                                interface.console.print("[yellow]No credentials stored.[/]")
                        elif parts[1] == "get" and len(parts) >= 3:
                            val = cm.get(parts[2])
                            if val:
                                interface.console.print(
                                    f"[green]{parts[2]}[/] = [bold]{val[:4]}...[/]"
                                )
                            else:
                                interface.console.print(f"[yellow]Key '{parts[2]}' not found.[/]")
                        elif parts[1] == "set" and len(parts) >= 4:
                            cm.set(parts[2], parts[3])
                            interface.console.print(
                                f"[green]Credential '{parts[2]}' stored securely.[/]"
                            )
                        elif parts[1] == "delete" and len(parts) >= 3:
                            if cm.delete(parts[2]):
                                interface.console.print(
                                    f"[green]Credential '{parts[2]}' deleted.[/]"
                                )
                            else:
                                interface.console.print(f"[yellow]Key '{parts[2]}' not found.[/]")
                        else:
                            interface.console.print(
                                "[red]Usage: /credentials <list|get|set|delete> [key] [value][/]"
                            )
                    except Exception as e:
                        interface.console.print(f"[red]Credential error: {e}[/]")
                continue

            if user_input.lower() == "/debug":
                if _viki_logger.level == logging.DEBUG:
                    _viki_logger.setLevel(logging.ERROR)
                    debug_state["active"] = False
                    interface.console.print("[yellow]Debug Mode: OFF (ERROR level)[/]")
                else:
                    _viki_logger.setLevel(logging.DEBUG)
                    debug_state["active"] = True
                    interface.console.print("[yellow]Debug Mode: ON (DEBUG level)[/]")
                continue

            import time

            start_t = time.time()
            streaming_state["active"] = False
            streaming_state["processing"] = True

            on_event("thought", "Thinking")

            response = await controller.process_request(user_input, on_event=on_event)

            streaming_state["processing"] = False
            if interface.status is not None:
                interface.status.stop()
                interface.status = None

            elapsed = time.time() - start_t

            if streaming_state["active"]:
                interface.console.print("")
                streaming_state["active"] = False
                in_fmt = interface.format_count(interface.session_usage["input"])
                out_fmt = interface.format_count(interface.session_usage["output"])
                interface.console.print(
                    f"\n[dim]   ({elapsed:.2f}s | Tokens: [bold cyan]{in_fmt}[/] in, [bold cyan]{out_fmt}[/] out)[/]"
                )
            else:
                in_fmt = interface.format_count(interface.session_usage["input"])
                out_fmt = interface.format_count(interface.session_usage["output"])
                interface.console.print(
                    f"\n[dim]   ({elapsed:.2f}s | Tokens: [bold cyan]{in_fmt}[/] in, [bold cyan]{out_fmt}[/] out)[/]"
                )
                interface.print_viki(response)

        except KeyboardInterrupt:
            break
        except Exception as e:
            interface.print_error(str(e))


async def main(workspace_path=None, query=None, dashboard=False, dashboard_port=8321):
    import asyncio
    import logging

    _silence_transformers()
    interface = SimpleInterface()
    _lazy_load_core()
    _viki_logger.setLevel(logging.INFO)

    debug_state = {"active": False}
    streaming_state = {"active": False, "processing": False}

    # Resolve config directory
    config_dir = None
    if os.environ.get("VIKI_CONFIG_DIR"):
        config_dir = os.environ["VIKI_CONFIG_DIR"]
    else:
        candidates = [
            os.path.join(os.getcwd(), "config"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"),
        ]
        for c in candidates:
            if os.path.exists(os.path.join(c, "settings.yaml")):
                config_dir = c
                break

    if not config_dir:
        raise FileNotFoundError(
            "Could not find config/settings.yaml. Set VIKI_CONFIG_DIR or run from project root."
        )

    settings_path = os.path.join(config_dir, "settings.yaml")

    # Run interactive onboarding for first-time users (only in interactive mode)
    if not query:
        _run_onboarding(settings_path)

    soul_path = _get_soul_path(settings_path)

    try:
        # Initialize Dependency Injection Container
        container = _Container()
        container.config.from_yaml(settings_path)

        controller = _VIKIController(settings_path, soul_path, workspace_override=workspace_path)

        # Inject dependencies into the controller (partial migration)
        controller.container = container
        controller.safety_service = container.safety_service()
        controller.recall_use_case = container.recall_memory_use_case()
        controller.swarm = container.swarm_orchestrator()

        # Self-Healing wiring
        self_healing = container.self_healing_service()
        self_healing.controller = controller
        controller.self_healing = self_healing

        # Forge wiring
        forge_orchestrator = container.forge_orchestrator()
        forge_orchestrator.controller = controller
        controller.forge_orchestrator = forge_orchestrator

    except Exception as e:
        import traceback

        _viki_logger.error(f"Initialization Failed: {e}")
        _viki_logger.error(traceback.format_exc())
        interface.print_error(f"Initialization Failed: {e}")
        return
    try:
        controller.attach_mcp_skills_sync()
    except Exception as e:
        _viki_logger.debug(f"MCP attach skipped: {e}")
    controller.check_skill_health()

    if dashboard:
        from viki.api.dashboard import run_dashboard

        runner = await run_dashboard(controller, port=dashboard_port)
        interface.console.print(
            f"[bold green]VIKI dashboard:[/] http://127.0.0.1:{dashboard_port}  (Ctrl+C to stop)"
        )
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await runner.cleanup()
            await controller.shutdown()
        return

    # Skip welcome panel for single queries (faster startup)
    if not query:
        interface.welcome(controller)

    def on_event(event_type, data):
        if event_type in ["thought", "action"]:
            if not streaming_state.get("processing", False) or streaming_state.get("active", False):
                return

            interface.last_thought = data
            in_fmt = interface.format_count(interface.session_usage["input"])
            out_fmt = interface.format_count(interface.session_usage["output"])
            tokens_str = f" [bold cyan]({in_fmt} | {out_fmt})[/]"
            if interface.status is None:
                interface.status = interface.console.status(
                    f"[dim]{data}...[/]{tokens_str}", spinner="dots"
                )
                interface.status.start()
            else:
                interface.status.update(f"[dim]{data}...[/]{tokens_str}")

            if debug_state["active"]:
                interface.console.print(f"[dim italic]{event_type}: {data}[/]")

        elif event_type == "usage":
            # Direct usage event from orchestrator or other components
            interface.session_usage["input"] += data.get("input", 0)
            interface.session_usage["output"] += data.get("output", 0)
            if interface.status:
                in_fmt = interface.format_count(interface.session_usage["input"])
                out_fmt = interface.format_count(interface.session_usage["output"])
                tokens_str = f" [bold cyan]({in_fmt} | {out_fmt})[/]"
                interface.status.update(f"[dim]{interface.last_thought}...[/]{tokens_str}")

        elif event_type == "status":
            pass  # Ignored by design to prevent background loop spinners

        elif event_type == "partial":
            if interface.status is not None:
                interface.status.stop()
                interface.status = None
            try:
                if not streaming_state["active"]:
                    interface.console.print("\n", end="")
                    streaming_state["active"] = True
                interface.console.print(str(data), end="")
            except Exception:
                pass
        elif event_type == "final":
            if interface.status is not None:
                interface.status.stop()
                interface.status = None
            if streaming_state["active"]:
                interface.console.print("\n")
                streaming_state["active"] = False
        elif event_type == "error":
            if interface.status is not None:
                interface.status.stop()
                interface.status = None
            interface.print_error(data)

    loop = asyncio.get_running_loop()

    # Start Usage Listener
    async def _usage_listener():
        import json

        from api.events import get_event_bus

        bus = get_event_bus()
        sub = bus.subscribe(channels=["system"])
        while True:
            try:
                msg = await sub.queue.get()
                payload = json.loads(msg)
                if payload.get("event") == "usage":
                    usage = payload.get("data", {})
                    on_event("usage", usage)
            except Exception:
                await asyncio.sleep(0.1)

    loop.create_task(_usage_listener())

    await _start_background_tasks(controller, on_event, loop, interface)

    if query:
        await _run_single_query(controller, interface, query, on_event, streaming_state)
    else:
        await _run_interactive_loop(controller, interface, on_event, streaming_state, debug_state)


def run():
    """Synchronous entry point for the `viki` console script."""
    import argparse

    parser = argparse.ArgumentParser(description="VIKI Sovereign Intelligence")
    parser.add_argument(
        "--low-resource",
        dest="low_resource",
        action="store_true",
        help="Optimize for local hardware: skip background cognitive loops",
    )
    parser.add_argument(
        "--reset", action="store_true", help="Reset user profile and trigger onboarding"
    )
    parser.add_argument(
        "--config-dir", dest="config_dir", help="Path to config directory containing settings.yaml"
    )
    parser.add_argument(
        "--setup",
        "--first-run",
        dest="setup",
        action="store_true",
        help="Run first-time setup (detect hardware, install deps, download models)",
    )
    parser.add_argument(
        "--check",
        dest="system_check",
        action="store_true",
        help="Run system check and print hardware report",
    )
    parser.add_argument(
        "--dashboard",
        dest="dashboard",
        action="store_true",
        help="Start the local web dashboard (chat, health, memory) instead of the CLI",
    )
    parser.add_argument(
        "--dashboard-port",
        dest="dashboard_port",
        type=int,
        default=8321,
        help="Port for --dashboard (default: 8321)",
    )
    parser.add_argument("args", nargs="*", help="Optional: [path] [query...]")
    parsed_args = parser.parse_args()

    if parsed_args.low_resource:
        os.environ["VIKI_LOW_RESOURCE"] = "true"

    if parsed_args.setup:
        return _run_setup()

    if parsed_args.system_check:
        return _run_system_check()

    if parsed_args.config_dir:
        os.environ["VIKI_CONFIG_DIR"] = parsed_args.config_dir

    if parsed_args.reset:
        config_dir = os.environ.get("VIKI_CONFIG_DIR")
        if not config_dir:
            candidates = [
                os.path.join(os.getcwd(), "config"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "config"),
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"),
            ]
            for c in candidates:
                if os.path.exists(os.path.join(c, "settings.yaml")):
                    config_dir = c
                    break
        if not config_dir:
            print("[red]Could not find config/settings.yaml for reset[/]")
            return
        settings_path = os.path.join(config_dir, "settings.yaml")
        if os.path.exists(settings_path):
            try:
                import yaml

                with open(settings_path, encoding="utf-8") as f:
                    settings = yaml.safe_load(f)

                system = settings.get("system", {})
                owner = system.get("owner", {})
                owner["name"] = "User"
                owner["role"] = "Developer"
                owner["custom_context"] = ""
                owner["interests"] = []

                with open(settings_path, "w", encoding="utf-8") as f:
                    yaml.dump(settings, f, default_flow_style=False, sort_keys=False)

                print("[bold yellow]Profile reset requested. Triggering onboarding...[/]")
            except Exception as e:
                print(f"[red]Error during reset: {e}[/]")

    workspace_path = None
    query_parts = []

    if parsed_args.args:
        first_arg = parsed_args.args[0]
        resolved = os.path.abspath(os.path.expanduser(first_arg))
        if os.path.isdir(resolved):
            workspace_path = resolved
            query_parts = parsed_args.args[1:]
        else:
            query_parts = parsed_args.args

    query_str = " ".join(query_parts).strip() if query_parts else None

    target_workspace = workspace_path if workspace_path else os.getcwd()

    console.print()
    console.print(
        Panel.fit(
            f"[bold white]Accessing workspace:[/]\n\n"
            f"[cyan]{target_workspace}[/]\n\n"
            f"Quick safety check: Is this a project you created or one you trust?\n"
            f"(Like your own code, a well-known open source project, or work from your team).\n"
            f"If not, take a moment to review what's in this folder first.\n\n"
            f"VIKI will be able to read, edit, and execute files here.",
            border_style="yellow",
            title="[bold yellow]Security Guide[/]",
        )
    )

    trust_env = os.environ.get("VIKI_TRUST_WORKSPACE", "").lower() in ("true", "1", "yes")
    if not trust_env and not Confirm.ask("Do you trust this folder and wish to proceed?"):
        console.print("[yellow]Access denied. Exiting.[/]")
        sys.exit(0)

    try:
        import asyncio

        asyncio.run(
            main(
                workspace_path=workspace_path,
                query=query_str,
                dashboard=parsed_args.dashboard,
                dashboard_port=parsed_args.dashboard_port,
            )
        )
    except KeyboardInterrupt:
        pass


def _run_setup():
    """Run the first-time setup orchestrator."""
    import asyncio

    from viki.bootstrap.installer import FirstRunOrchestrator

    orchestrator = FirstRunOrchestrator()
    success = asyncio.run(orchestrator.run())
    if success:
        print("\n[bold green]Setup complete. Run 'python -m viki' to start the assistant.[/]")
    else:
        print(
            "\n[red]Setup was not completed. You can run it again with 'python -m viki --setup'.[/]"
        )


def _run_system_check():
    """Run system detection and print hardware report."""
    import asyncio

    from viki.bootstrap.system_detector import SystemDetector

    async def _check():
        detector = SystemDetector()
        info = await detector.detect()
        print(detector.format_report(info))

    asyncio.run(_check())


if __name__ == "__main__":
    run()
