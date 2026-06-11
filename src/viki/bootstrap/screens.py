"""Rich terminal screens for the VIKI installer."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from viki.bootstrap.dependency_manager import DependencyResult, DepStatus
from viki.bootstrap.model_manager import ModelInfo
from viki.bootstrap.system_detector import HardwareProfile, SystemInfo


def make_console() -> Console:
    return Console(legacy_windows=False)


def show_banner(console: Console) -> None:
    banner = Text(
        """
    ╔══════════════════════════════════════════════╗
    ║                                              ║
    ║     ██╗   ██╗██╗██╗  ██╗██╗                ║
    ║     ██║   ██║██║██║ ██╔╝██║                ║
    ║     ██║   ██║██║█████╔╝ ██║                ║
    ║     ╚██╗ ██╔╝██║██╔═██╗ ██║                ║
    ║      ╚████╔╝ ██║██║  ██╗██║                ║
    ║       ╚═══╝  ╚═╝╚═╝  ╚═╝╚═╝                ║
    ║                                              ║
    ║     Self-Installing Local AI Platform        ║
    ║                                              ║
    ╚══════════════════════════════════════════════╝
    """,
        style="bold cyan",
    )
    console.print(banner)


def show_system_report(console: Console, info: SystemInfo, profile: HardwareProfile) -> None:
    table = Table(title="System Detection", box=box.ROUNDED, expand=True)
    table.add_column("Component", style="bold cyan")
    table.add_column("Detected", style="white")

    table.add_row("OS", f"{info.os_name} ({info.os_version})")
    table.add_row("CPU", f"{info.cpu_model}")
    table.add_row("Cores", f"{info.cpu_cores}C / {info.cpu_threads}T")
    table.add_row("RAM", f"{info.ram_mb / 1024:.1f} GB")
    table.add_row("Storage", f"{info.storage_free_mb / 1024:.1f} GB free")

    if info.gpus:
        for i, gpu in enumerate(info.gpus):
            table.add_row(f"GPU {i}", f"{gpu.model} ({gpu.vram_mb} MB VRAM)")
    else:
        table.add_row("GPU", "[yellow]None detected (CPU mode)[/]")

    table.add_row("Python", info.python_version)
    table.add_row(
        "Profile", f"[green]{profile.tier}[/] — {profile.recommended_mode.value} mode recommended"
    )

    console.print(Panel(table, border_style="cyan"))


def show_dependency_table(console: Console, results: list[DependencyResult]) -> None:
    table = Table(title="Dependency Check", box=box.SIMPLE, expand=True)
    table.add_column("Dependency", style="bold")
    table.add_column("Status", style="bold")
    table.add_column("Version", style="dim")
    table.add_column("Required", style="dim")

    for dep in results:
        if dep.status == DepStatus.OK:
            status = "[green]OK[/]"
        elif dep.status == DepStatus.MISSING:
            status = "[red]Missing[/]"
        elif dep.status == DepStatus.WRONG_VERSION:
            status = f"[yellow]Update needed ({dep.version} → {dep.required_version})[/]"
        else:
            status = "[red]Error[/]"
        table.add_row(dep.name, status, dep.version, dep.required_version)

    console.print(Panel(table, border_style="blue"))


def show_model_recommendation(
    console: Console,
    primary: ModelInfo | None,
    fallback: ModelInfo | None,
    embedding: ModelInfo | None,
) -> None:
    if not primary:
        console.print("[yellow]No model recommendations available for this hardware.[/]")
        return

    table = Table(title="Recommended Models", box=box.ROUNDED, expand=True)
    table.add_column("Role", style="bold cyan")
    table.add_column("Model", style="white")
    table.add_column("Size", style="dim")
    table.add_column("Disk", style="dim")

    table.add_row(
        "[green]Primary[/]",
        primary.name,
        primary.parameter_count,
        f"{primary.disk_size_mb // 1024} GB",
    )
    if fallback:
        table.add_row(
            "[yellow]Fallback[/]",
            fallback.name,
            fallback.parameter_count,
            f"{fallback.disk_size_mb // 1024} GB",
        )
    if embedding:
        table.add_row(
            "[blue]Embeddings[/]",
            embedding.name,
            embedding.parameter_count,
            f"{embedding.disk_size_mb // 1024} MB",
        )

    console.print(Panel(table, border_style="green"))


def make_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=Console(legacy_windows=False),
    )


def confirm_step(console: Console, title: str, message: str, details: str = "") -> bool:
    """Ask for user confirmation with a rich panel."""
    from rich.prompt import Confirm

    console.print()
    console.print(
        Panel(
            f"{message}\n\n[dim]{details}[/]" if details else message,
            title=f"[bold yellow]{title}[/]",
            border_style="yellow",
        )
    )
    return Confirm.ask("\nProceed?", default=True)
