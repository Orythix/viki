"""V2 MCP integration — wraps MCP server tools as V2 BaseTool instances."""

from .client import V2MCPClient
from .config import MCPServerSpec, load_mcp_config
from .tool import MCPTool, register_mcp_tools, register_mcp_tools_async

__all__ = [
    "V2MCPClient",
    "MCPServerSpec",
    "load_mcp_config",
    "MCPTool",
    "register_mcp_tools",
    "register_mcp_tools_async",
]
