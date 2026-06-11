"""v2 CLI entry point."""

from __future__ import annotations

import asyncio
import json

from .core.intent_analyzer import IntentAnalyzer
from .core.permission_manager import PermissionManager
from .core.tool_selector import ToolSelector
from .providers import create_provider
from .tools.network.tool import NetworkTool
from .tools.registry import ToolRegistry
from .tools.system.tool import SystemTool


async def main():
    provider = create_provider()
    registry = ToolRegistry()
    registry.register(SystemTool(provider=provider))
    registry.register(NetworkTool(provider=provider))

    intent_analyzer = IntentAnalyzer()
    PermissionManager(tool_registry=registry)
    tool_selector = ToolSelector(tool_registry=registry)

    print(f"[VIKI v2] Platform: {provider.PLATFORM}")
    print("[VIKI v2] Type 'exit' to quit.")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        intent = intent_analyzer.analyze(user_input)

        if intent:
            result = await registry.execute(intent.tool, intent.params, provider=provider)
            print(json.dumps(result.data, indent=2, default=str))
        else:
            tool_result = tool_selector.select_tool(user_input)
            if tool_result:
                name, params = tool_result
                result = await registry.execute(name, params, provider=provider)
                print(
                    json.dumps(result.data, indent=2, default=str)
                    if result.success
                    else f"Error: {result.error}"
                )
            else:
                print("Could not determine intent. Try rephrasing.")


if __name__ == "__main__":
    asyncio.run(main())
