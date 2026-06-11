"""First-run orchestrator — full setup pipeline for VIKI."""

from __future__ import annotations

import os

from rich.console import Console
from rich.prompt import Prompt

from viki.bootstrap.dependency_manager import DependencyManager
from viki.bootstrap.model_manager import ModelInfo, ModelManager
from viki.bootstrap.screens import (
    confirm_step,
    make_progress,
    show_banner,
    show_dependency_table,
    show_model_recommendation,
    show_system_report,
)
from viki.bootstrap.system_detector import (
    HardwareProfile,
    InstallMode,
    SystemDetector,
    SystemInfo,
)


class FirstRunOrchestrator:
    """Full first-run setup pipeline.

    Pipeline:
        detect() → check_deps() → install_deps() → recommend_models()
        → download_models() → configure() → launch()
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console(legacy_windows=False)
        self.detector = SystemDetector()
        self.dep_manager: DependencyManager | None = None
        self.model_manager = ModelManager()
        self.system_info: SystemInfo | None = None
        self.profile: HardwareProfile | None = None
        self.selected_mode: InstallMode = InstallMode.LIGHT
        self.models_to_download: list[ModelInfo] = []

    async def run(self) -> bool:
        """Execute the full first-run pipeline. Returns True if setup completed."""
        show_banner(self.console)

        # Step 1: Detect system
        if not await self._step_detect():
            return False

        # Step 2: Check dependencies
        if not await self._step_check_deps():
            return False

        # Step 3: Install dependencies
        if not await self._step_install_deps():
            return False

        # Step 4: Recommend models
        if not await self._step_recommend_models():
            return False

        # Step 5: Download models
        if not await self._step_download_models():
            return False

        # Step 6: Configure
        if not await self._step_configure():
            return False

        # Step 7: Done
        self._show_complete()
        return True

    async def _step_detect(self) -> bool:
        self.console.rule("[bold cyan]Step 1: System Detection")
        self.console.print(
            "[dim]Detecting operating system, hardware, and compute capabilities...[/]\n"
        )

        self.system_info = await self.detector.detect()
        self.profile = self.detector.get_profile()

        show_system_report(self.console, self.system_info, self.profile)

        # Ask for install mode
        self.console.print("\n[bold]Installation Mode:[/]")
        self.console.print(
            "  [green]1.[/] Light    — Minimal, fast startup, low RAM [dim](recommended for your hardware)[/]"
        )
        self.console.print("  [green]2.[/] Developer — Git, terminal tools, code analysis")
        self.console.print(
            "  [green]3.[/] Advanced  — Agent framework, local memory, security monitoring"
        )

        mode_map = {"1": InstallMode.LIGHT, "2": InstallMode.DEVELOPER, "3": InstallMode.ADVANCED}
        default_mode = "1" if self.profile.recommended_mode == InstallMode.LIGHT else "2"

        choice = Prompt.ask(
            "Select mode",
            choices=["1", "2", "3"],
            default=default_mode,
        )
        self.selected_mode = mode_map[choice]
        self.dep_manager = DependencyManager(interactive=True, mode=self.selected_mode.value)
        return True

    async def _step_check_deps(self) -> bool:
        self.console.rule("[bold blue]Step 2: Dependency Check")
        self.console.print("[dim]Checking installed dependencies...[/]\n")

        results = await self.dep_manager.check_all()
        show_dependency_table(self.console, results)

        missing = self.dep_manager.get_missing()
        if not missing:
            self.console.print("[bold green]All dependencies satisfied![/]\n")
            return True

        self.console.print(f"\n[bold yellow]{len(missing)} dependencies need attention.[/]")
        total_size = sum(d.size_mb for d in missing)
        if total_size > 0:
            self.console.print(f"Estimated download: {total_size / 1024:.1f} GB")

        return True

    async def _step_install_deps(self) -> bool:
        missing = self.dep_manager.get_missing()
        if not missing:
            return True

        self.console.rule("[bold yellow]Step 3: Install Dependencies")
        self.console.print()

        for dep in missing:
            details = ""
            if dep.size_mb > 0:
                details = f"Size: {dep.size_mb / 1024:.1f} GB"
            if dep.install_hint:
                details += f"\nManual: {dep.install_hint}"

            proceed = confirm_step(
                self.console,
                "Install Dependency?",
                f"[bold]{dep.name}[/] is [red]missing[/].\nRequired: {dep.required_version}",
                details,
            )
            if not proceed:
                self.console.print(
                    f"  [yellow]Skipping {dep.name}. You can install manually later.[/]"
                )
                continue

            self.console.print(f"  Installing [bold]{dep.name}[/]...")
            success = await self.dep_manager._install_one(dep)
            if success:
                dep.status = "ok"
                self.console.print(f"  [green]✓ {dep.name} installed[/]")
            else:
                self.console.print(f"  [red]✗ Failed to install {dep.name}[/]")

        return True

    async def _step_recommend_models(self) -> bool:
        self.console.rule("[bold green]Step 4: Model Recommendation")
        self.console.print("[dim]Analyzing hardware to recommend optimal AI models...[/]\n")

        rec = self.model_manager.recommend(self.system_info, self.profile)
        show_model_recommendation(self.console, rec.primary, rec.fallback, rec.embedding)

        if not rec.primary:
            self.console.print("[yellow]No suitable models found for this hardware.[/]")
            return True

        self.models_to_download = []
        if rec.primary:
            self.models_to_download.append(rec.primary)
        if rec.embedding:
            self.models_to_download.append(rec.embedding)
        if rec.fallback and self.selected_mode != InstallMode.LIGHT:
            self.models_to_download.append(rec.fallback)

        total_disk = await self.model_manager.get_disk_required(self.models_to_download)
        self.console.print(f"\nTotal download: ~{total_disk / 1024:.1f} GB")

        proceed = confirm_step(
            self.console,
            "Download Models",
            f"Download {len(self.models_to_download)} recommended model(s)?",
            f"Estimated size: {total_disk / 1024:.1f} GB\nNetwork usage: One-time download from Ollama registry",
        )

        if not proceed:
            self.models_to_download = []
            self.console.print(
                "[yellow]Skipping model download. You can pull models later with 'ollama pull <model>'.[/]"
            )

        return True

    async def _step_download_models(self) -> bool:
        if not self.models_to_download:
            return True

        self.console.rule("[bold green]Step 5: Download Models")
        self.console.print()

        for model in self.models_to_download:
            installed = await self.model_manager.is_installed(model.id)
            if installed:
                self.console.print(f"  [green]✓ {model.name} already installed[/]")
                continue

            self.console.print(
                f"\n  Downloading [bold]{model.name}[/] ({model.disk_size_mb // 1024} GB)..."
            )
            _progress_bar = make_progress()
            _task_id = _progress_bar.add_task(f"  Pulling {model.id}...", total=100)

            async def _make_callback(pb, tid):
                async def on_progress(msg: str):
                    if "%" in msg:
                        try:
                            pct = int(msg.split("%")[0].split()[-1])
                            pb.update(tid, completed=pct)
                        except (ValueError, IndexError):
                            pass

                return on_progress

            callback = await _make_callback(_progress_bar, _task_id)
            with _progress_bar:
                success = await self.model_manager.download(model, progress_callback=callback)

            if success:
                self.console.print(f"  [green]✓ {model.name} ready[/]")
            else:
                self.console.print(f"  [red]✗ Failed to download {model.name}[/]")

        return True

    async def _step_configure(self) -> bool:
        self.console.rule("[bold magenta]Step 6: Configuration")
        self.console.print("[dim]Setting up VIKI configuration...[/]\n")

        # Create default config directories
        config_dir = os.environ.get("VIKI_CONFIG_DIR") or os.path.join(os.getcwd(), "config")
        data_dir = os.environ.get("VIKI_DATA_DIR") or os.path.join(os.getcwd(), "data")
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)

        # Write basic settings.yaml if it doesn't exist
        settings_path = os.path.join(config_dir, "settings.yaml")
        if not os.path.exists(settings_path):
            self.console.print(f"  Creating default configuration at [dim]{settings_path}[/]")
            owner_name = Prompt.ask("  Your name", default="User")
            owner_role = Prompt.ask("  Your role", default="Developer")

            settings = f"""# VIKI configuration — generated by bootstrap
system:
  log_level: "INFO"
  data_dir: "{data_dir}"
  workspace_dir: "{os.getcwd()}"
  persona: sovereign
  low_resource: {"true" if self.selected_mode == InstallMode.LIGHT else "false"}
  owner:
    name: "{owner_name}"
    role: "{owner_role}"

models:
  default: {"gemma4:12b" if self.profile and self.profile.can_run_14b else "phi3:mini"}
  providers:
    ollama:
      type: local
      base_url: http://localhost:11434
"""
            with open(settings_path, "w") as f:
                f.write(settings)
            self.console.print("  [green]✓ Configuration created[/]")

        # Set Ollama host for container users
        if self.system_info and self.system_info.is_container:
            self.console.print(
                "  [yellow]Container detected: set OLLAMA_HOST=host.docker.internal:11434[/]"
            )

        self.console.print("  [green]✓ Configuration complete[/]\n")
        return True

    def _show_complete(self) -> None:
        from rich.panel import Panel
        from rich.text import Text

        self.console.rule("[bold green]Setup Complete!")
        self.console.print()

        content = Text(
            """
    VIKI is ready to launch.

    Start the assistant:
        python -m viki

    Quick commands:
        /help       — Show available commands
        /train      — Evolve VIKI's capabilities
        /credentials — Manage API keys
        /boundary   — Security dashboard

    Documentation:
        docs/ folder in your project directory

    The system is eternal. Knowledge is power.
    """,
            style="bold green",
        )

        self.console.print(Panel(content, border_style="green"))
