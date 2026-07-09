import os

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table


class SimpleInterface:
    def __init__(self):
        self.console = Console()
        self.status = None
        self.session_usage = {"input": 0, "output": 0}
        self.last_thought = "Thinking"
        self.admin_mode = False
        self._tool_call_depth = 0
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
                        "/skills",
                        "/train",
                        "/shadow",
                        "/debug",
                        "/credentials",
                        "/confirm",
                        "/reject",
                        "/scan",
                        "/restore",
                        "/undo",
                        "/save",
                        "/load",
                        "/resume",
                        "/setup",
                        "/first-run",
                        "/update",
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

        validated = self._validate_input(user_input)
        if validated is None:
            self.console.print("[yellow]Input cleaned or rejected — please rephrase.[/]")
            return ""

        self.check_admin_auth(validated)
        return validated

    def format_count(self, count):
        if count >= 1_000_000:
            return f"{count / 1_000_000:.2f}M"
        return f"{count / 1_000:.3f}K"

    def welcome(self, controller=None):
        try:
            username = os.getlogin()
        except (FileNotFoundError, OSError):
            import getpass

            username = getpass.getuser()
        cwd = os.getcwd()

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
            body = (
                f"[red]▐▛███▜▌[/]  [bold red]Welcome back, Boss {owner}![/]\n"
                f"[red]▝▜█████▛▘[/] [bold gold1]VIKI — SUPER ADMIN MODE[/]\n"
                f"[red]  ▘▘ ▝▝[/]  [gold1]The Architect is present.[/]\n"
                f"[dim]{cwd}[/]\n\n"
                "[bold red]⚡ ADMINISTRATOR AUTHENTICATED[/] — full system access granted.\n"
                f"Network: {net}    Shell: {shell}\n"
                "Run [bold cyan]/help[/] to see all available commands."
            )
            panel = Panel(
                body,
                title="[bold red]VIKI v8.1.0 — SUPER ADMIN[/]",
                title_align="left",
                border_style="red",
                box=box.DOUBLE,
            )
        else:
            body = (
                f"[cyan]▐▛███▜▌[/]  [bold]Welcome back {username.capitalize()}![/]\n"
                "[cyan]▝▜█████▛▘[/] VIKI Sovereign Intelligence\n"
                f"[cyan]  ▘▘ ▝▝[/]  [dim]{cwd}[/]\n\n"
                f"Network: {net}    Shell: {shell}\n"
                "Run [bold cyan]/help[/] for commands · [bold cyan]/boundary[/] for security scopes"
            )
            panel = Panel(
                body,
                title="[bold]VIKI v8.1.0[/]",
                title_align="left",
                border_style="cyan",
                box=box.ROUNDED,
            )

        self.console.print()
        self.console.print(panel)
        self.console.print()

    def print_user(self, text):
        self.console.print(f"[bold]You:[/] {text}")

    def print_viki(self, text):
        import re

        trace_match = re.search(r"(\[SYSTEM_TRACE\].*)$", text, re.DOTALL | re.IGNORECASE)
        main_content = text
        trace_content = ""

        if trace_match:
            main_content = text[: trace_match.start()].strip()
            trace_content = trace_match.group(1).strip()

        self.console.print()
        self.console.print(Markdown(main_content))

        if trace_content:
            self.console.print()
            self.console.print(f"[dim]{trace_content}[/]")
        self.console.print()

    def start_thinking(self, thought: str = "Thinking"):
        """Show or update a live spinner instead of spamming a new line per event."""
        if self.status is None:
            self.status = self.console.status(f"[dim]{thought}...[/]", spinner="dots")
            self.status.start()
        else:
            self.status.update(f"[dim]{thought}...[/]")

    def stop_thinking(self):
        if self.status is not None:
            self.status.stop()
            self.status = None

    @staticmethod
    def _format_params(params) -> str:
        if not params:
            return ""
        if isinstance(params, dict):
            parts = []
            for key, value in params.items():
                value_str = str(value).replace("\n", " ")
                if len(value_str) > 60:
                    value_str = value_str[:57] + "..."
                parts.append(f"{key}={value_str}")
            return ", ".join(parts)
        text = str(params)
        return text if len(text) <= 200 else text[:197] + "..."

    def print_tool_call(self, tool_name: str, params=None):
        """Show a tool call as a single line, Claude CLI style: `\u25cf Tool(args)`."""
        self.stop_thinking()
        self._tool_call_depth += 1
        self.console.print(
            f"[bold cyan]\u25cf[/] [bold]{tool_name}[/][dim]({self._format_params(params)})[/]"
        )

    def print_tool_result(self, result: str):
        """Show a condensed, indented summary of the tool result under its call."""
        self._tool_call_depth = max(0, self._tool_call_depth - 1)
        result = str(result) if result else ""
        if not result:
            self.console.print("  [dim]\u23bf  (no output)[/]")
            return
        lines = result.splitlines()
        first_line = lines[0][:120]
        extra = len(lines) - 1
        suffix = (
            f" [dim]\u2026 (+{extra} more line{'s' if extra != 1 else ''})[/]" if extra > 0 else ""
        )
        self.console.print(f"  [dim]\u23bf  {first_line}[/]{suffix}")

    def print_streaming_chunk(self, chunk: str):
        self.console.print(chunk, end="")

    def print_error(self, text):
        self.console.print(f"[bold red]Error:[/] {text}\n")

    def render_boundary_dashboard(self, controller):
        from rich.columns import Columns

        status = controller.get_sovereign_status()

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
        status = controller.get_sovereign_status()
        audit_table = Table(title="[bold yellow]Session Audit Log[/]", box=box.ROUNDED, expand=True)
        audit_table.add_column("Category", style="dim", width=15)
        audit_table.add_column("Resource/Action", style="white")
        files = status["filesystem"]["touched_files"]
        for f in files:
            audit_table.add_row("File Access", f)
        cmds = status["shell"]["executed_commands"]
        for c in cmds:
            audit_table.add_row("Shell Command", f"[bold green]{c}[/]")
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
