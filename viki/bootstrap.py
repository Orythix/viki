import os
import sys
import warnings

# Aggressively suppress HuggingFace and Transformers noise
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", module="sentence_transformers")
warnings.filterwarnings("ignore", module="transformers")

# Force transformers logging level directly if the library is loaded
try:
    import transformers
    transformers.logging.set_verbosity_error()
except ImportError:
    pass
import asyncio
import time
import argparse
import subprocess
import webbrowser
import logging
from datetime import datetime
from dotenv import load_dotenv

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

load_dotenv()

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from viki.core.orchestrator import VIKIController
from viki.config.logger import viki_logger
from viki.config.resolve import get_soul_path
from viki.service_registry import Container
from viki.core.utils.onboarding import run_onboarding

console = Console()

class SimpleInterface:
    def __init__(self):
        self.console = Console()
        self.status = None
        self.session_usage = {"input": 0, "output": 0}
        self.last_thought = "Thinking"
        
    def format_count(self, count):
        if count >= 1_000_000:
            return f"{count / 1_000_000:.2f}M"
        return f"{count / 1_000:.3f}K"

    def welcome(self, controller=None):
        import os
        username = os.getlogin() if hasattr(os, "getlogin") else "User"
        cwd = os.getcwd()
        
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
        
        net = "[bold green]ONLINE[/]"
        shell = "[bold green]ENABLED[/]"
        if controller:
            status = controller.get_sovereign_status()
            net = "[bold red]AIR-GAPPED[/]" if status["network"]["air_gap"] else "[bold green]ONLINE[/]"
            shell = "[bold green]ENABLED[/]" if status["shell"]["enabled"] else "[bold red]DISABLED[/]"
            
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
        
        grid = Table(show_header=False, show_edge=False, box=box.MINIMAL, padding=(1, 3), expand=True)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="left", ratio=2)
        grid.add_row(left_content, right_content)
        
        panel = Panel(
            grid,
            title="[bold]VIKI v8.1.0[/]",
            title_align="left",
            border_style="cyan",
            box=box.ROUNDED,
            expand=True
        )
        
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def print_user(self, text):
        pass # Input prompt handles this cleanly now

    def print_viki(self, text):
        from rich.markdown import Markdown
        from rich.panel import Panel
        import re

        # Separate system traces from the final response if present
        trace_match = re.search(r"(\[SYSTEM_TRACE\].*)$", text, re.DOTALL | re.IGNORECASE)
        main_content = text
        trace_content = ""
        
        if trace_match:
            main_content = text[:trace_match.start()].strip()
            trace_content = trace_match.group(1).strip()

        # Render main response in a clean panel
        self.console.print(Panel(
            Markdown(main_content),
            title="[bold magenta]VIKI[/]",
            title_align="left",
            border_style="magenta",
            padding=(1, 2)
        ))

        # Render trace content in a subtle, dimmed way if it exists
        if trace_content:
            self.console.print(Panel(
                f"[dim]{trace_content}[/]",
                title="[dim]System Trace[/]",
                border_style="dim",
                padding=(0, 1)
            ))
        self.console.print()
        
    def print_error(self, text):
        self.console.print(f"[bold red]Error:[/] {text}\n")
        
    def print_thought(self, text):
        pass # Handled by spinner

    def print_action(self, text):
        pass # Handled by spinner

    def render_boundary_dashboard(self, controller):
        """Renders the dashboard panel showing the current security boundaries when requested."""
        status = controller.get_sovereign_status()
        
        fs_table = Table.grid(expand=True)
        fs_table.add_column(style="cyan", justify="left")
        fs_table.add_column(style="white", justify="left")
        fs_table.add_row("Workspace:", status["filesystem"]["workspace"])
        fs_table.add_row("Scope:", f"{status['filesystem']['allowed_roots_count']} Allowed Roots")

        net_table = Table.grid(expand=True)
        net_table.add_column(style="cyan", justify="left")
        net_table.add_column(style="white", justify="left")
        net_val = "[bold red]AIR-GAPPED[/]" if status["network"]["air_gap"] else "[bold green]ONLINE[/]"
        net_table.add_row("Network:", net_val)
        shell_val = "[bold green]ENABLED[/]" if status["shell"]["enabled"] else "[bold red]DISABLED[/]"
        net_table.add_row("Shell:", shell_val)

        panel_content = Columns([fs_table, net_table])
        self.console.print(Panel(panel_content, title="[bold blue]SOVEREIGN BOUNDARY[/]", border_style="blue"))

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
        viki_logger.debug(f"Error stopping bridges: {e}")
    await controller.shutdown()

async def _start_background_tasks(controller, on_event, loop, interface):
    try:
        await controller.bio.start()
        controller._create_tracked_task(controller.nexus.start_processing(on_event=on_event), "nexus_processing")
        try:
             for bridge_name in ("telegram", "discord", "slack", "whatsapp"):
                 bridge = getattr(controller, bridge_name, None)
                 if bridge is not None and hasattr(bridge, "start"):
                     await bridge.start()
        except Exception as bridge_err:
             viki_logger.warning(f"One or more external bridges failed to initialize: {bridge_err}")
        
        if getattr(controller, "low_resource_mode", False):
            viki_logger.info("low_resource_mode: skipping wellness/dream/reflector/watchdog loops.")
        else:
            controller._create_tracked_task(controller.wellness.start(), "wellness_monitoring")
            controller._create_tracked_task(controller.dream.start_monitoring(), "dream_monitoring")
            controller._create_tracked_task(controller.reflector.reflect_on_logs(), "log_reflection")
            controller.watchdog.start(loop)
    except Exception as e:
        interface.print_error(f"Task Launch Error: {e}")

async def _run_single_query(controller, interface, query, on_event, streaming_state):
    try:
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
            user_input = interface.console.input("\n> ").strip()
            
            if not user_input: continue
            if user_input.lower() in ["exit", "quit", "/exit"]:
                interface.console.print("[yellow]Shutting down...[/]")
                await _shutdown_controller(controller)
                break
            
            if user_input.lower() == "/reset":
                if Confirm.ask("[bold red]Are you sure you want to completely wipe VIKI's memory? This cannot be undone.[/]"):
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
                                interface.console.print(f"[red]Failed to delete {os.path.basename(db_file)}: {e}[/]")
                                
                    interface.console.print(f"[bold green]Memory wiped ({deleted_count} files deleted). Please restart VIKI to start fresh.[/]")
                    break
                else:
                    interface.console.print("[dim]Reset cancelled.[/]")
                continue
            
            if user_input.lower() == "/help":
                interface.console.print("[bold cyan]Available Commands:[/]")
                interface.console.print("  [green]/help[/]     — Show this help")
                interface.console.print("  [green]/skills[/]   — List all registered skills")
                interface.console.print("  [green]/train[/]    — Trigger Neural Forge to evolve VIKI (bake memories into model)")
                interface.console.print("  [green]/shadow[/]   — Toggle shadow mode (simulate vs real execution)")
                interface.console.print("  [green]/debug[/]    — Toggle debug logging")
                interface.console.print("  [green]/exit[/]     — Shutdown VIKI")
                interface.console.print("  [green]/confirm[/]  — Confirm pending action (or reply yes/confirm)")
                interface.console.print("  [green]/reject[/]    — Cancel pending action (or reply no/reject)")
                interface.console.print("  [green]/scan[/]     — Re-scan workspace codebase (use in chat)")
                interface.console.print("  [green]/restore[/]  — List checkpoints; /restore <id> to revert files")
                interface.console.print("  [green]/undo[/]     — Roll back the most recent checkpoint")
                interface.console.print("  [green]/reset[/]    — Wipe VIKI's memory databases and start fresh")
                interface.console.print("  [green]/save[/]     — Save session: /save <name>")
                interface.console.print("  [green]/load[/]     — Load session: /load <name>")
                interface.console.print("  [green]/boundary[/] — Refresh the Sovereign Boundary dashboard")
                continue

            if user_input.lower() == "/train":
                interface.console.print("[bold blue]Initiating Neural Forge Evolution...[/]")
                from viki.evolution_engine import main_forge
                success = main_forge()
                if success:
                    interface.console.print("[bold green]Evolution successful! Evolved model 'viki-evolved' is now updated.[/]")
                else:
                    interface.console.print("[bold red]Evolution failed. Check logs for details.[/]")
                continue
            
            if user_input.lower() == "/boundary":
                interface.render_boundary_dashboard(controller)
                continue
            
            if user_input.lower() == "/skills":
                interface.console.print("[bold cyan]Registered Skills:[/]")
                for name, skill in controller.skill_registry.skills.items():
                    metrics = controller.skill_registry.get_reliability_score(name)
                    desc = skill.description[:60] if hasattr(skill, 'description') else '—'
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
            
            if user_input.lower() == "/debug":
                if viki_logger.level == logging.DEBUG:
                    viki_logger.setLevel(logging.ERROR)
                    debug_state["active"] = False
                    interface.console.print("[yellow]Debug Mode: OFF (ERROR level)[/]")
                else:
                    viki_logger.setLevel(logging.DEBUG)
                    debug_state["active"] = True
                    interface.console.print("[yellow]Debug Mode: ON (DEBUG level)[/]")
                continue
                
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
                in_fmt = interface.format_count(interface.session_usage['input'])
                out_fmt = interface.format_count(interface.session_usage['output'])
                interface.console.print(f"\n[dim]   ({elapsed:.2f}s | Tokens: [bold cyan]{in_fmt}[/] in, [bold cyan]{out_fmt}[/] out)[/]")
            else:
                in_fmt = interface.format_count(interface.session_usage['input'])
                out_fmt = interface.format_count(interface.session_usage['output'])
                interface.console.print(f"\n[dim]   ({elapsed:.2f}s | Tokens: [bold cyan]{in_fmt}[/] in, [bold cyan]{out_fmt}[/] out)[/]")
                interface.print_viki(response)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            interface.print_error(str(e))

async def main(workspace_path=None, query=None):
    interface = SimpleInterface()
    viki_logger.setLevel(logging.INFO)
    
    debug_state = {"active": False}
    streaming_state = {"active": False, "processing": False}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "config", "settings.yaml")
    
    # Run interactive onboarding for first-time users
    if not query:
        run_onboarding(settings_path)
        
    soul_path = get_soul_path(settings_path)

    try:
        # Initialize Dependency Injection Container
        container = Container()
        # Wire configuration to the container
        container.config.from_yaml(settings_path)
        
        controller = VIKIController(settings_path, soul_path, workspace_override=workspace_path)
        
        # Inject dependencies into the controller (partial migration)
        # Note: Eventually VIKIController will be fully managed by the container.
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
        viki_logger.error(f"Initialization Failed: {e}")
        viki_logger.error(traceback.format_exc())
        interface.print_error(f"Initialization Failed: {e}")
        return
    try:
        controller.attach_mcp_skills_sync()
    except Exception as e:
        viki_logger.debug(f"MCP attach skipped: {e}")
    controller.check_skill_health()
    interface.welcome(controller)

    def on_event(event_type, data):
        if event_type in ["thought", "action"]:
            if not streaming_state.get("processing", False) or streaming_state.get("active", False):
                return
                
            interface.last_thought = data
            in_fmt = interface.format_count(interface.session_usage['input'])
            out_fmt = interface.format_count(interface.session_usage['output'])
            tokens_str = f" [bold cyan]({in_fmt} | {out_fmt})[/]"
            if interface.status is None:
                interface.status = interface.console.status(f"[dim]{data}...[/]{tokens_str}", spinner="dots")
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
                in_fmt = interface.format_count(interface.session_usage['input'])
                out_fmt = interface.format_count(interface.session_usage['output'])
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
        from viki.api.events import get_event_bus
        import json
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
    parser = argparse.ArgumentParser(description="VIKI Sovereign Intelligence")
    parser.add_argument("--low-resource", dest="low_resource", action="store_true", help="Optimize for local hardware: skip background cognitive loops")
    parser.add_argument("--reset", action="store_true", help="Reset user profile and trigger onboarding")
    parser.add_argument("args", nargs="*", help="Optional: [path] [query...]")
    parsed_args = parser.parse_args()

    if parsed_args.low_resource:
        os.environ["VIKI_LOW_RESOURCE"] = "true"

    if parsed_args.reset:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        settings_path = os.path.join(script_dir, "config", "settings.yaml")
        if os.path.exists(settings_path):
            try:
                import yaml
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = yaml.safe_load(f)
                
                # Reset owner details
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
        # Check if first argument is an existing directory
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
    console.print(Panel.fit(
        f"[bold white]Accessing workspace:[/]\n\n"
        f"[cyan]{target_workspace}[/]\n\n"
        f"Quick safety check: Is this a project you created or one you trust?\n"
        f"(Like your own code, a well-known open source project, or work from your team).\n"
        f"If not, take a moment to review what's in this folder first.\n\n"
        f"VIKI will be able to read, edit, and execute files here.",
        border_style="yellow",
        title="[bold yellow]Security Guide[/]"
    ))
    
    if not Confirm.ask("Do you trust this folder and wish to proceed?"):
        console.print("[yellow]Access denied. Exiting.[/]")
        sys.exit(0)

    try:
        asyncio.run(main(workspace_path=workspace_path, query=query_str))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
