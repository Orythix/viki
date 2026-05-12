import os
import sys
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

load_dotenv()

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from viki.core.controller import VIKIController
from viki.config.logger import viki_logger
from viki.config.resolve import get_soul_path
from viki.container import Container

console = Console()

class SimpleInterface:
    def __init__(self):
        self.console = Console()
        self.status_spinner = None
        
    def welcome(self, controller=None):
        self.console.print("[bold magenta]VIKI v7.0[/] [dim]System Online[/]")
        if controller is not None:
            persona = getattr(controller, "persona", "sovereign")
            diff = controller.get_differentiators() if hasattr(controller, "get_differentiators") else []
            first_diff = diff[0] if diff else "Orythix"
            self.console.print(f"[dim]Persona: {persona} | {first_diff}[/]")
            if hasattr(controller, "get_runtime_health_summary"):
                health_summary = controller.get_runtime_health_summary()
                style = "yellow" if "degraded" in health_summary else "dim"
                self.console.print(f"[{style}]{health_summary}[/]")
        self.console.print("[dim]Type 'exit' to quit.[/]\n")

    def print_user(self, text):
        self.console.print(f"[bold green]USER >[/] {text}")

    def print_viki(self, text):
        self.console.print(f"[bold cyan]VIKI >[/] {text}\n")
        
    def print_error(self, text):
        self.console.print(f"[bold red]ERROR >[/] {text}")
        
    def print_thought(self, text):
        # Subtle thought logging
        self.console.print(f"[dim italic]   Thinking: {text}[/]")

    def print_action(self, text):
        self.console.print(f"[yellow]   Action: {text}[/]")

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
        response = await controller.process_request(query, on_event=on_event)
        elapsed = time.time() - start_t

        if streaming_state["active"]:
            interface.console.print("")
            streaming_state["active"] = False
            interface.console.print(f"[dim]   ({elapsed:.2f}s)[/]")
        else:
            interface.console.print(f"[dim]   ({elapsed:.2f}s)[/]")
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
            user_input = interface.console.input("[bold green]USER > [/]").strip()
            
            if not user_input: continue
            if user_input.lower() in ["exit", "quit", "/exit"]:
                interface.console.print("[yellow]Shutting down...[/]")
                await _shutdown_controller(controller)
                break
            
            if user_input.lower() == "/help":
                interface.console.print("[bold cyan]Available Commands:[/]")
                interface.console.print("  [green]/help[/]     — Show this help")
                interface.console.print("  [green]/skills[/]   — List all registered skills")
                interface.console.print("  [green]/shadow[/]   — Toggle shadow mode (simulate vs real execution)")
                interface.console.print("  [green]/debug[/]    — Toggle debug logging")
                interface.console.print("  [green]/exit[/]     — Shutdown VIKI")
                interface.console.print("  [green]/confirm[/]  — Confirm pending action (or reply yes/confirm)")
                interface.console.print("  [green]/reject[/]    — Cancel pending action (or reply no/reject)")
                interface.console.print("  [green]/scan[/]     — Re-scan workspace codebase (use in chat)")
                interface.console.print("  [green]/restore[/]  — List checkpoints; /restore <id> to revert files")
                interface.console.print("  [green]/undo[/]     — Roll back the most recent checkpoint")
                interface.console.print("  [green]/save[/]     — Save session: /save <name>")
                interface.console.print("  [green]/load[/]     — Load session: /load <name>")
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
            response = await controller.process_request(user_input, on_event=on_event)
            elapsed = time.time() - start_t

            if streaming_state["active"]:
                interface.console.print("")
                streaming_state["active"] = False
                interface.console.print(f"[dim]   ({elapsed:.2f}s)[/]")
            else:
                interface.console.print(f"[dim]   ({elapsed:.2f}s)[/]")
                interface.print_viki(response)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            interface.print_error(str(e))

async def main(workspace_path=None, query=None):
    interface = SimpleInterface()
    viki_logger.setLevel(logging.ERROR)
    
    debug_state = {"active": False}
    streaming_state = {"active": False}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "config", "settings.yaml")
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
        
    except Exception as e:
        interface.print_error(f"Initialization Failed: {e}")
        return
    try:
        controller.attach_mcp_skills_sync()
    except Exception as e:
        viki_logger.debug(f"MCP attach skipped: {e}")
    controller.check_skill_health()
    interface.welcome(controller)

    def on_event(event_type, data):
        if event_type == "thought":
            if debug_state["active"]:
                interface.print_thought(data)
        elif event_type == "action":
            if debug_state["active"]:
                interface.print_action(str(data))
        elif event_type == "partial":
            try:
                if not streaming_state["active"]:
                    interface.console.print("[bold cyan]VIKI > [/]", end="")
                    streaming_state["active"] = True
                interface.console.print(str(data), end="")
            except Exception:
                pass
        elif event_type == "final":
            if streaming_state["active"]:
                interface.console.print("")
                streaming_state["active"] = False
        elif event_type == "status":
            pass  # Ignored by design
        elif event_type == "error":
            interface.print_error(data)

    loop = asyncio.get_running_loop()
    await _start_background_tasks(controller, on_event, loop, interface)

    if query:
        await _run_single_query(controller, interface, query, on_event, streaming_state)
    else:
        await _run_interactive_loop(controller, interface, on_event, streaming_state, debug_state)

def run():
    """Synchronous entry point for the `viki` console script."""
    parser = argparse.ArgumentParser(description="VIKI Sovereign Intelligence")
    parser.add_argument("--ui", "--face-ui", dest="ui", action="store_true", help="Start API server and open hologram face UI in browser")
    parser.add_argument("args", nargs="*", help="Optional: [path] [query...]")
    parsed_args = parser.parse_args()

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

    api_process = None
    if parsed_args.ui:
        # Start Flask API server in background so the UI can talk to VIKI
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)
        server_script = os.path.join(script_dir, "api", "server.py")
        try:
            api_process = subprocess.Popen(
                [sys.executable, server_script],
                cwd=parent_dir,
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            time.sleep(2.5)
            console.print("[dim]API server started. Hologram UI: http://localhost:5173[/]")
            console.print("[dim]Start the UI with: cd ui && npm run dev[/]\n")
            try:
                webbrowser.open("http://localhost:5173")
            except Exception as e:
                viki_logger.debug("Open browser: %s", e)
        except Exception as e:
            viki_logger.warning(f"Could not start API server or open browser: {e}")

    try:
        asyncio.run(main(workspace_path=workspace_path, query=query_str))
    except KeyboardInterrupt:
        pass
    finally:
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            api_process.wait(timeout=5)


if __name__ == "__main__":
    run()
