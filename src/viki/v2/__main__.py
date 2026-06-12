"""V2 CLI entry point with Rich TUI — streaming tokens, workflow/agent progress."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from .config import V2Config, get_config, parse_cli_overrides, watch_config
from .core import CoreAgent, PermissionManager, PermissionTier
from .providers import create_provider
from .tools.registry import ToolRegistry
from .workflow.definitions import list_workflows

try:
    from .tools.mcp import register_mcp_tools_async
except ImportError:
    register_mcp_tools_async = None

console = Console()


async def confirm_callback(tool_name: str, params: dict, tier: PermissionTier) -> bool:
    """Async confirmation callback for admin actions."""
    console.print(
        Panel(
            f"[bold yellow]⚠ Admin Action Required[/bold yellow]\n\n"
            f"Tool: [cyan]{tool_name}[/cyan]\n"
            f"Action: [cyan]{params.get('action', params.get('query', 'execute'))}[/cyan]\n"
            f"Params: {params}\n"
            f"Risk: [red]{tier.name}[/red]",
            title="Confirmation Required",
            border_style="yellow",
        )
    )
    response = Prompt.ask("Approve?", choices=["y", "n"], default="n")
    return response == "y"


def _build_status_table(
    agents: dict[str, str] | None = None,
    workflow_steps: dict[str, bool | None] | None = None,
) -> Table | None:
    """Build a small status table for active workflows/agents, or None if idle."""
    table = Table.grid(padding=(0, 2))
    has_rows = False
    if agents:
        table.add_column("Agent", style="cyan")
        table.add_column("Status", style="bold")
        for name, status in agents.items():
            icon = "⏳" if status == "start" else "✅"
            style = "yellow" if status == "start" else "green"
            table.add_row(name, f"[{style}]{icon} {status.title()}[/{style}]")
            has_rows = True
    if workflow_steps:
        table.add_column("Step", style="cyan")
        table.add_column("Status", style="bold")
        for name, status in workflow_steps.items():
            if status is None:
                icon, style, label = "⏳", "yellow", "Running"
            elif status:
                icon, style, label = "✅", "green", "OK"
            else:
                icon, style, label = "❌", "red", "Failed"
            table.add_row(name, f"[{style}]{icon} {label}[/{style}]")
            has_rows = True
    return table if has_rows else None


async def process_with_streaming(
    agent: CoreAgent,
    user_input: str,
    round_num: int = 0,
) -> str:
    """Run agent.process() with live streaming of tokens and progress."""
    tokens: list[str] = []
    agent_statuses: dict[str, str] = {}
    workflow_steps: dict[str, bool | None] = {}
    response_text = Text("Thinking...", style="dim italic")
    tokens_plain: list[str] = []

    def _make_panel() -> Panel:
        children = [Panel(response_text, title=f"Response #{round_num}", border_style="green")]
        status_table = _build_status_table(
            agents=agent_statuses or None,
            workflow_steps=workflow_steps or None,
        )
        if status_table:
            children.append(Panel(status_table, title="Progress", border_style="blue"))
        return Panel(Group(*children), title="VIKI v2")

    def on_token(token: str):
        tokens.append(token)
        tokens_plain.append(token)
        response_text.append(token)

    def on_workflow_step(_wf: str, step_name: str, status: bool | None):
        workflow_steps[step_name] = status

    def on_agent_status(agent_name: str, status: str):
        agent_statuses[agent_name] = status

    with Live(
        _make_panel(),
        refresh_per_second=15,
        console=console,
    ) as live:

        def _update():
            live.update(_make_panel())

        def on_token_live(token: str):
            on_token(token)
            _update()

        def on_workflow_step_live(wf: str, step: str, status: bool | None):
            on_workflow_step(wf, step, status)
            _update()

        def on_agent_status_live(name: str, status: str):
            on_agent_status(name, status)
            _update()

        response = await agent.process(
            user_input,
            on_token=on_token_live,
            on_workflow_step=on_workflow_step_live,
            on_agent_status=on_agent_status_live,
        )

    if "".join(tokens_plain) != response:
        console.print(Markdown(response))
    return response


async def main():
    cli_overrides, parsed = parse_cli_overrides()

    if parsed.generate_schema:
        path = V2Config.generate_schema_file()
        print(f"JSON Schema written to {path}")
        sys.exit(0)

    if parsed.config:
        cfg = get_config(parsed.config, cli_overrides=cli_overrides)
    else:
        cfg = get_config(cli_overrides=cli_overrides)

    provider = create_provider()
    registry = ToolRegistry()

    # Run tool discovery, MCP registration, and plugin loading concurrently
    tools_dir = Path(__file__).parent / "tools"

    async def _discover_builtins():
        return await asyncio.to_thread(registry.discover, str(tools_dir))

    async def _register_mcp():
        if register_mcp_tools_async is not None:
            return await register_mcp_tools_async(registry, config_path=cfg.mcp_config_path)
        return 0

    async def _discover_plugins():
        counts = []
        for plugin_dir_str in cfg.plugin_dirs:
            plugin_dir = Path(plugin_dir_str)
            if plugin_dir.is_dir():
                count = registry.discover_plugins(str(plugin_dir))
                if count:
                    console.print(f"[dim]Plugins: {count} tools loaded from {plugin_dir_str}[/dim]")
                counts.append(count)
        default_plugin_dir = Path.home() / ".viki" / "plugins"
        if default_plugin_dir.is_dir() and str(default_plugin_dir) not in cfg.plugin_dirs:
            count = registry.discover_plugins(str(default_plugin_dir))
            if count:
                console.print(f"[dim]Plugins: {count} tools loaded[/dim]")
            counts.append(count)
        return counts

    discovered, mcp_count, _ = await asyncio.gather(
        _discover_builtins(),
        _register_mcp(),
        _discover_plugins(),
    )
    if mcp_count:
        console.print(f"[dim]MCP: {mcp_count} tools registered[/dim]")

    perm_manager = PermissionManager(registry)
    perm_manager.set_confirm_callback(confirm_callback)

    agent = CoreAgent(tool_registry=registry, permission_manager=perm_manager, config=cfg)

    console.print(
        Panel(
            f"[bold green]VIKI v2[/bold green] — Local-First AI Agent\n"
            f"Platform: [cyan]{provider.PLATFORM}[/cyan]\n"
            f"Model: [cyan]{cfg.model}[/cyan]\n"
            f"Tools: [cyan]{', '.join(registry.list_tools())}[/cyan]"
            f" [dim]({discovered} discovered)[/dim]\n"
            f"Specialist agents: [cyan]{len(agent.agent_manager.list_agents())}[/cyan]\n"
            f"Workflows: [cyan]{', '.join(list_workflows())}[/cyan]\n\n"
            f"Type 'exit' or 'quit' to leave.",
            title="VIKI v2",
            border_style="green",
        )
    )

    config_watch_task = None
    if parsed.watch:

        async def watch_and_apply():
            async for new_cfg in watch_config():
                if new_cfg.log_level != cfg.log_level:
                    import logging

                    logging.getLogger().setLevel(new_cfg.log_level)
                console.print(f"[dim]Config reloaded: model={new_cfg.model}[/dim]")

        config_watch_task = asyncio.create_task(watch_and_apply())

    round_num = 0
    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        try:
            round_num += 1
            await process_with_streaming(agent, user_input, round_num=round_num)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    if config_watch_task is not None:
        config_watch_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
