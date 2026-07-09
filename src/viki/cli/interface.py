import os

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


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
