import os
import sys
import asyncio
import time
import argparse
import subprocess
import webbrowser
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

console = Console()

class SimpleInterface:
    def __init__(self):
        self.console = Console()
        self.status_spinner = None
        
    def welcome(self):
        self.console.print("[bold magenta]VIKI v7.0[/] [dim]System Online[/]")
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

async def main():
    interface = SimpleInterface()
    interface.welcome()
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(script_dir, "config", "settings.yaml")
    soul_path = os.path.join(script_dir, "config", "soul.yaml")
    
    try:
        controller = VIKIController(settings_path, soul_path)
    except Exception as e:
        interface.print_error(f"Initialization Failed: {e}")
        return

    # Event Handler for linear logging
    def on_event(event_type, data):
        if event_type == "thought":
            interface.print_thought(data)
        elif event_type == "action":
            interface.print_action(str(data))
        elif event_type == "status":
            pass # Ignore status updates in simple mode to reduce noise
        elif event_type == "error":
            interface.print_error(data)

    try:
        # Background Tasks
        loop = asyncio.get_running_loop()
        await controller.bio.start()
        controller._create_tracked_task(controller.nexus.start_processing(on_event=on_event), "nexus_processing")
        try:
             await controller.telegram.start()
             await controller.discord.start()
             await controller.slack.start()
             await controller.whatsapp.start()
        except Exception as bridge_err:
             viki_logger.warning(f"One or more external bridges failed to initialize: {bridge_err}")
        
        controller._create_tracked_task(controller.wellness.start(), "wellness_monitoring")
        controller._create_tracked_task(controller.dream.start_monitoring(), "dream_monitoring")
        controller._create_tracked_task(controller.reflector.reflect_on_logs(), "log_reflection")
        controller.watchdog.start(loop)
    except Exception as e:
        interface.print_error(f"Task Launch Error: {e}")

    # Main Interaction Loop
    while True:
        try:
            # Clean Input
            user_input = interface.console.input("[bold green]USER > [/]").strip()
            
            if not user_input: continue
            if user_input.lower() in ["exit", "quit", "/exit"]:
                interface.console.print("[yellow]Shutting down...[/]")
                controller.watchdog.stop()
                controller.bio.stop()
                controller.nexus.stop()
                try: 
                    await controller.discord.stop()
                    await controller.telegram.stop() 
                except Exception as e:
                    viki_logger.debug(f"Error stopping bridges: {e}")
                await controller.shutdown()
                break
            
            # --- CLI Commands ---
            if user_input.lower() == "/help":
                interface.console.print("[bold cyan]Available Commands:[/]")
                interface.console.print("  [green]/help[/]     — Show this help")
                interface.console.print("  [green]/skills[/]   — List all registered skills")
                interface.console.print("  [green]/shadow[/]   — Toggle shadow mode (simulate vs real execution)")
                interface.console.print("  [green]/debug[/]    — Toggle debug logging")
                interface.console.print("  [green]/exit[/]     — Shutdown VIKI")
                continue
            
            if user_input.lower() == "/skills":
                interface.console.print("[bold cyan]Registered Skills:[/]")
                for name, skill in controller.skill_registry.skills.items():
                    metrics = controller.skill_registry.get_reliability_score(name)
                    desc = skill.description[:60] if hasattr(skill, 'description') else '—'
                    interface.console.print(f"  [green]{name:20s}[/] {desc} [dim]{metrics}[/]")
                continue
            
            if user_input.lower() == "/shadow":
                controller.shadow_mode = not controller.shadow_mode
                state = "ON (simulation only)" if controller.shadow_mode else "OFF (real execution)"
                interface.console.print(f"[yellow]Shadow Mode: {state}[/]")
                continue
            
            if user_input.lower() == "/debug":
                import logging
                logger = logging.getLogger("viki")
                if logger.level == logging.DEBUG:
                    logger.setLevel(logging.INFO)
                    interface.console.print("[yellow]Debug Mode: OFF (INFO level)[/]")
                else:
                    logger.setLevel(logging.DEBUG)
                    interface.console.print("[yellow]Debug Mode: ON (DEBUG level)[/]")
                continue
                
            # Processing with Spinner
            with interface.console.status("[bold cyan]Thinking...", spinner="dots"):
                start_t = time.time()
                response = await controller.process_request(user_input, on_event=on_event)
                elapsed = time.time() - start_t
            
            # Print Final Response
            interface.console.print(f"[dim]   ({elapsed:.2f}s)[/]")
            interface.print_viki(response)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            interface.print_error(str(e))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VIKI Sovereign Intelligence")
    parser.add_argument("--ui", "--face-ui", dest="ui", action="store_true", help="Start API server and open hologram face UI in browser")
    args = parser.parse_args()

    api_process = None
    if args.ui:
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
            webbrowser.open("http://localhost:5173")
            console.print("[dim]API server started. Hologram UI: http://localhost:5173[/]")
            console.print("[dim]Start the UI with: cd ui && npm run dev[/]\n")
        except Exception as e:
            viki_logger.warning(f"Could not start API server or open browser: {e}")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            api_process.wait(timeout=5)
