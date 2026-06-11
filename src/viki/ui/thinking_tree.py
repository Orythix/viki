from rich.console import RenderableType
from rich.panel import Panel
from rich.tree import Tree


class ThinkingTree:
    """Renders a real-time visualization of VIKI's cognitive routing decision-tree."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.root = Tree("🧠 [bold cyan]VIKI Consciousness Stack[/]")
        self.perception = self.root.add("👂 [dim]Perception[/]")
        self.interpretation = self.root.add("🔍 [dim]Interpretation[/]")
        self.deliberation = self.root.add("⚖️ [dim]Deliberation[/]")
        self.execution = self.root.add("🚀 [dim]Execution[/]")

    def update_perception(self, data: str):
        self.perception.label = f"👂 [bold green]Perception[/]: [italic]{data}[/]"

    def update_interpretation(self, intent: str, capabilities: list, sentiment: str):
        self.interpretation.label = "🔍 [bold green]Interpretation[/]"
        self.interpretation.add(f"Intent: [yellow]{intent}[/]")
        self.interpretation.add(f"Sentiment: [magenta]{sentiment}[/]")
        self.interpretation.add(f"Caps: [blue]{', '.join(capabilities)}[/]")

    def update_deliberation(self, model: str, tier: str, thoughts: str = None):
        self.deliberation.label = "⚖️ [bold green]Deliberation[/]"
        self.deliberation.add(f"Model: [cyan]{model}[/] (Tier: [bold]{tier}[/])")
        if thoughts:
            self.deliberation.add(f"Plan: [italic white]{thoughts[:50]}...[/]")

    def update_execution(self, tool: str, params: dict = None):
        self.execution.label = "🚀 [bold green]Execution[/]"
        call = f"[bold yellow]{tool}[/]"
        if params:
            call += f"({params})"
        self.execution.add(call)

    def __rich__(self) -> RenderableType:
        return Panel(self.root, title="[bold]Thinking[/]", border_style="cyan")
