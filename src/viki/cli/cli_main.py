import logging
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from viki.cli import loader as _lazy_mod
from viki.cli.interface import SimpleInterface


def _enable_windows_vt():
    """Enable ANSI/VT processing on the native Windows console.

    Without this, Rich can't detect VT support and falls back to its legacy
    Windows renderer, which has a known bug that duplicates multi-column
    panel content (e.g. the welcome/boundary dashboards) taller than one
    screenful. Must run before the first `Console()` is constructed, since
    Rich caches the legacy-Windows detection on first use.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | enable_vt)
    except Exception:
        pass


_enable_windows_vt()

console = Console()

# Optional: pyperclip for /paste support
try:
    import pyperclip
except ImportError:
    pyperclip = None


def _silence_transformers():
    try:
        import transformers

        transformers.logging.set_verbosity_error()
    except ImportError:
        pass


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
        _lazy_mod._viki_logger.debug(f"Error stopping bridges: {e}")
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
            _lazy_mod._viki_logger.warning(
                f"One or more external bridges failed to initialize: {bridge_err}"
            )

        if getattr(controller, "low_resource_mode", False):
            _lazy_mod._viki_logger.info(
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
        interface.stop_thinking()

        elapsed = time.time() - start_t
        if not streaming_state["active"]:
            interface.print_viki(response)
        interface.console.print(f"\n[dim]   ({elapsed:.2f}s)[/]")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        interface.print_error(str(e))
    finally:
        interface.stop_thinking()
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
                    "  [green]/train-lora[/] [tag] — Real LoRA fine-tune on accumulated lessons (needs torch/peft/trl)"
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
                from viki.evolution_engine import main_forge

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

            if user_input.lower().startswith("/train-lora"):
                if not hasattr(controller, "forge_orchestrator"):
                    interface.console.print("[bold red]Forge orchestrator is not available.[/]")
                    continue
                parts = user_input.split(maxsplit=1)
                target_tag = (
                    parts[1].strip() if len(parts) > 1 and parts[1].strip() else "viki-lora"
                )
                interface.console.print(
                    f"[bold blue]Initiating LoRA fine-tune → '{target_tag}' "
                    "(exporting lessons, then training; this can take a while)...[/]"
                )
                result = await controller.forge_orchestrator.bake_lora(target_tag=target_tag)
                if result.startswith("Forge LoRA Success"):
                    interface.console.print(f"[bold green]{result}[/]")
                else:
                    interface.console.print(f"[bold red]{result}[/]")
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
                if _lazy_mod._viki_logger.level == logging.DEBUG:
                    _lazy_mod._viki_logger.setLevel(logging.ERROR)
                    debug_state["active"] = False
                    interface.console.print("[yellow]Debug Mode: OFF (ERROR level)[/]")
                else:
                    _lazy_mod._viki_logger.setLevel(logging.DEBUG)
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
            interface.stop_thinking()
            was_streaming = streaming_state["active"]
            streaming_state["active"] = False

            elapsed = time.time() - start_t
            if not was_streaming:
                interface.print_viki(response)

            in_fmt = interface.format_count(interface.session_usage["input"])
            out_fmt = interface.format_count(interface.session_usage["output"])
            interface.console.print(
                f"\n[dim]   ({elapsed:.2f}s | Tokens: [bold cyan]{in_fmt}[/] in, [bold cyan]{out_fmt}[/] out)[/]"
            )

        except KeyboardInterrupt:
            interface.stop_thinking()
            break
        except Exception as e:
            interface.stop_thinking()
            interface.print_error(str(e))


async def main(workspace_path=None, query=None, dashboard=False, dashboard_port=8321):
    import asyncio
    import logging

    _silence_transformers()
    interface = SimpleInterface()
    _lazy_mod._lazy_load_core()
    _lazy_mod._viki_logger.setLevel(logging.INFO)

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
        _lazy_mod._run_onboarding(settings_path)

    soul_path = _lazy_mod._get_soul_path(settings_path)

    try:
        # Initialize Dependency Injection Container
        container = _lazy_mod._Container()
        container.config.from_yaml(settings_path)

        controller = _lazy_mod._VIKIController(
            settings_path, soul_path, workspace_override=workspace_path
        )

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

        _lazy_mod._viki_logger.error(f"Initialization Failed: {e}")
        _lazy_mod._viki_logger.error(traceback.format_exc())
        interface.print_error(f"Initialization Failed: {e}")
        return
    try:
        controller.attach_mcp_skills_sync()
    except Exception as e:
        _lazy_mod._viki_logger.debug(f"MCP attach skipped: {e}")
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
            if streaming_state.get("active"):
                return
            interface.last_thought = str(data)[:80]
            interface.start_thinking(interface.last_thought)
            if debug_state["active"]:
                interface.console.print(f"[dim italic]{event_type}: {data}[/]")

        elif event_type == "usage":
            interface.session_usage["input"] += data.get("input", 0)
            interface.session_usage["output"] += data.get("output", 0)

        elif event_type == "status":
            msg = str(data)
            if msg.startswith(("EXECUTING ", "REFLEX EXECUTING ", "THINKING ")):
                pass  # rendered via the "tool_call" event / thinking spinner instead
            elif debug_state["active"]:
                interface.console.print(f"[dim]{msg}[/]")

        elif event_type == "tool_call":
            name = data.get("name", "tool")
            interface.print_tool_call(name, data.get("params", {}))

        elif event_type == "tool_result":
            interface.print_tool_result(str(data))

        elif event_type == "partial":
            try:
                interface.stop_thinking()
                if not streaming_state["active"]:
                    interface.console.print()
                    streaming_state["active"] = True
                interface.print_streaming_chunk(str(data))
            except Exception:
                logging.getLogger(__name__).warning("failed to render streaming partial")
        elif event_type == "final":
            interface.stop_thinking()
            if streaming_state["active"]:
                interface.console.print()
                streaming_state["active"] = False
        elif event_type == "error":
            interface.stop_thinking()
            if streaming_state["active"]:
                interface.console.print()
                streaming_state["active"] = False
            interface.print_error(data)

    loop = asyncio.get_running_loop()

    # Start Usage Listener
    async def _usage_listener():
        import json

        from viki.api.events import get_event_bus

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

    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if getattr(stream, "encoding", "").lower() != "utf-8":
                stream.reconfigure(encoding="utf-8")

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
        "--config-dir",
        dest="config_dir",
        help="Path to config directory containing settings.yaml",
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
