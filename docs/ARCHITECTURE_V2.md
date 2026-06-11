# VIKI v2 — Local-First AI Operating System Agent

> **Architecture Design Document**
> Principal AI Systems Architect Review

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Component Diagram](#2-component-diagram)
3. [Folder Structure](#3-folder-structure)
4. [Class Design](#4-class-design)
5. [Tool Registry Design](#5-tool-registry-design)
6. [Permission System](#6-permission-system)
7. [Memory System](#7-memory-system)
8. [Intent Analysis Workflow](#8-intent-analysis-workflow)
9. [Tool Selection Workflow](#9-tool-selection-workflow)
10. [Python Implementation Examples](#10-python-implementation-examples)
11. [Cross-Platform Strategy](#11-cross-platform-strategy)
12. [Error Handling Strategy](#12-error-handling-strategy)
13. [Security Recommendations](#13-security-recommendations)
14. [Scalability Recommendations & Long-Term Vision](#14-scalability-recommendations--long-term-vision)
15. [Multi-Agent System](#15-multi-agent-system)
16. [Task Planning Engine](#16-task-planning-engine)
17. [Self-Critique & Reflection](#17-self-critique--reflection)
18. [Autonomous Workflows](#18-autonomous-workflows)
19. [Repository Intelligence](#19-repository-intelligence)
20. [Tool Discovery & Auto-Registration](#20-tool-discovery--auto-registration)
21. [Context Manager & Project Memory](#21-context-manager--project-memory)
22. [Engineering-Specific Features](#22-engineering-specific-features)
23. [Migration Plan for Existing VIKI Codebase](#23-migration-plan-for-existing-viki-codebase)

---

## 1. High-Level Architecture

### Architecture Philosophy

VIKI v2 transitions from a **chatbot with tools** to an **agent operating system** where the LLM is the reasoning kernel and every OS interaction goes through a structured, permission-gated tool layer.

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                          │
│   CLI    Terminal    API    Web UI    IDE Plugin    Chat Bridge  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                        INPUT PIPELINE                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │SuperAdmin│→ │Governor  │→ │Safety    │→ │Intent Classifier  │ │
│  │  Layer   │  │  Check   │  │Sanitize  │  │(LLM-based)        │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┬───────┘ │
└──────────────────────────────────────────────────────────┼───────┘
                                                           │
┌──────────────────────────────────────────────────────────▼───────┐
│                      REASONING KERNEL                             │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  CORE AGENT (LLM Session)                    │  │
│  │  • System prompt with full context                          │  │
│  │  • Tool definitions injected                                │  │
│  │  • ReAct loop (Reason → Act → Observe)                      │  │
│  │  • Self-validation before response                          │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                      │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │                INTENT ROUTER                                 │  │
│  │  • LLM-based semantic classification (not keyword matching)  │  │
│  │  • Maps user intent → tool(s)                                │  │
│  │  • Extracts parameters from natural language                 │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                      │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │                TOOL SELECTION ENGINE                         │  │
│  │  • Tool descriptions + examples → LLM chooses               │  │
│  │  • No hardcoded keyword-to-tool mappings                    │  │
│  │  • Multi-tool orchestration for complex tasks               │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────┐
│                      EXECUTION LAYER                               │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │Permission│→ │Tool      │→ │Execution │→ │Output Validator   │ │
│  │ Manager  │  │ Registry │  │  Engine  │  │                   │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘ │
│       │              │              │                             │
│       ▼              ▼              ▼                             │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              SYSTEM PROVIDERS (OS Layer)                  │     │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │     │
│  │  │Windows   │  │Linux     │  │Mac       │               │     │
│  │  │Provider  │  │Provider  │  │Provider  │               │     │
│  │  └──────────┘  └──────────┘  └──────────┘               │     │
│  └─────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────────────┐
│                     MEMORY SYSTEM                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐ │
│  │ Session     │  │ Project     │  │ Long-Term (SQLite/Vector)  │ │
│  │ Memory      │  │ Memory      │  │ • Preferences             │ │
│  │ • History   │  │ • Repo ctx  │  │ • Learned patterns        │ │
│  │ • State     │  │ • Tasks     │  │ • User knowledge          │ │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LLM-based intent routing** | Eliminates fragile keyword matching. "What is my WiFi password?" and "Show my wireless key" route to the same tool via semantic similarity |
| **Tool descriptions drive selection** | The LLM chooses tools by reading their name, description, capabilities, and examples — not hardcoded mappings |
| **System Provider abstraction** | All OS interactions go through `SystemProvider` → `WindowsProvider`|`LinuxProvider`|`MacProvider`. The agent never calls OS APIs directly |
| **Three-tier permission model** | SAFE (no confirmation), ELEVATED (user notified), ADMIN (explicit confirmation required) |
| **ReAct loop with validation** | Each action is validated before and after execution. Loop continues until goal is met or max steps reached |
| **Project memory** | Tracks active project, stack, open issues, decisions, and context across sessions |

---

## 2. Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            VIKI v2 SYSTEM                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  USER INTERFACES                                                         ││
│  │  ┌─────────┐ ┌──────────┐ ┌──────┐ ┌─────┐ ┌──────────┐ ┌───────────┐ ││
│  │  │ CLI     │ │ Terminal │ │ API  │ │ Web │ │ IDE      │ │ Chat      │ ││
│  │  │ (rich)  │ │ (stdio)  │ │(Fast │ │ UI  │ │ Plugin   │ │ Bridges   │ ││
│  │  │         │ │          │ │API)  │ │     │ │ (LSP)    │ │(TG/Disc)  │ ││
│  │  └────┬────┘ └────┬─────┘ └──┬───┘ └──┬──┘ └────┬─────┘ └─────┬─────┘ ││
│  └───────┼───────────┼──────────┼─────────┼──────────┼─────────────┼───────┘│
│          │           │          │         │          │             │        │
│  ┌───────▼───────────▼──────────▼─────────▼──────────▼─────────────▼───────┐│
│  │  INPUT NEXUS (unified message queue with priority)                       ││
│  │  Routes all inputs to the same processing pipeline                      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│  ┌────────────────────────────────▼─────────────────────────────────────────┐│
│  │  PREFLIGHT PIPELINE                                                       ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐ ││
│  │  │Auth Check│→│Governor  │→│Safety    │→│Cache Hit │→│Memory Context │ ││
│  │  │(Super    │ │(Ethical) │ │Sanitize  │ │(Semantic)│ │Retrieval      │ ││
│  │  │Admin)    │ │          │ │          │ │          │ │               │ ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────┬───────┘ ││
│  └────────────────────────────────────────────────────────────────┼─────────┘│
│                                                                   │          │
│  ┌───────────────────────────────────────────────────────────────▼─────────┐│
│  │  REASONING KERNEL                                                        ││
│  │                                                                          ││
│  │  ┌─────────────────────────────────────────────────────────────────────┐││
│  │  │  INTENT ANALYZER (LLM-based)                                         │││
│  │  │  • Classifies user goal from natural language                       │││
│  │  │  • Output: structured intent object                                 │││
│  │  │  • No keyword lists or regex patterns                               │││
│  │  └────────────────────────────────┬────────────────────────────────────┘││
│  │                                   │                                      ││
│  │  ┌───────────────────────────────▼──────────────────────────────────────┐││
│  │  │  TOOL SELECTOR (LLM-based)                                            │││
│  │  │  • Reads tool registry definitions (name, desc, capabilities, ex)    │││
│  │  │  • LLM selects best tool for intent + parameters                     │││
│  │  │  • Falls back to asking user if uncertain                            │││
│  │  └────────────────────────────────┬────────────────────────────────────┘││
│  │                                   │                                      ││
│  │  ┌───────────────────────────────▼──────────────────────────────────────┐││
│  │  │  REACT LOOP (up to N steps)                                          │││
│  │  │  • Step 1: LLM reasons → selects action                              │││
│  │  │  • Step 2: Permission check                                          │││
│  │  │  • Step 3: Execute tool                                              │││
│  │  │  • Step 4: Observe result → feed back to LLM                        │││
│  │  │  • Step 5: Repeat or finalize                                        │││
│  │  └─────────────────────────────────────────────────────────────────────┘││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│  ┌────────────────────────────────▼─────────────────────────────────────────┐│
│  │  EXECUTION LAYER                                                          ││
│  │                                                                          ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ││
│  │  │ Permission   │  │ Tool         │  │ Execution    │  │ Response     │ ││
│  │  │ Manager      │→ │ Registry     │→ │ Engine       │→ │ Generator    │ ││
│  │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │ ││
│  │  │ │ SAFE     │ │  │ │SystemTool│ │  │ │ Timeout  │ │  │ │ Format   │ │ ││
│  │  │ │ ELEVATED │ │  │ │FSTool    │ │  │ │ Sandbox  │ │  │ │ Markdown │ │ ││
│  │  │ │ ADMIN    │ │  │ │ShellTool │ │  │ │ Stream   │ │  │ │ Symbols  │ │ ││
│  │  │ └──────────┘ │  │ │GitTool   │ │  │ │ Capture  │ │  │ │ Sections │ │ ││
│  │  │              │  │ │DBTool    │ │  │ └──────────┘ │  │ └──────────┘ │ ││
│  │  │              │  │ │NetTool   │ │  │              │  │              │ ││
│  │  │              │  │ │DevTool   │ │  │              │  │              │ ││
│  │  │              │  │ └──────────┘ │  │              │  │              │ ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│  ┌────────────────────────────────▼─────────────────────────────────────────┐│
│  │  SYSTEM PROVIDERS (Abstract OS Layer)                                     ││
│  │  ┌──────────────────────────────────────────────────────────────────────┐││
│  │  │  SystemProvider (abstract base)                                       │││
│  │  │  ├── WindowsProvider (powershell, wmic, netsh, reg query)             │││
│  │  │  ├── LinuxProvider (bash, /proc, sysfs, ip, nmcli)                    │││
│  │  │  └── MacProvider (zsh, system_profiler, networksetup, scutil)         │││
│  │  └──────────────────────────────────────────────────────────────────────┘││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                                    │                                         │
│  ┌────────────────────────────────▼─────────────────────────────────────────┐│
│  │  MEMORY SYSTEM                                                            ││
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────────┐  ││
│  │  │ Session Memory │  │ Project Memory │  │ Long-Term Memory           │  ││
│  │  │ • Conversation │  │ • Active repo  │  │ • Preferences             │  ││
│  │  │ • Turn state   │  │ • Stack/tools  │  │ • Learned patterns        │  ││
│  │  │ • Temp data    │  │ • Open issues  │  │ • User knowledge          │  ││
│  │  │                │  │ • Decisions    │  │ • Tool usage history      │  ││
│  │  └────────────────┘  └────────────────┘  │ • Security baseline       │  ││
│  │                                           └────────────────────────────┘  ││
│  └──────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Folder Structure

```
src/viki/v2/
│
├── __init__.py
│
├── core/
│   ├── __init__.py
│   ├── agent.py                  # CoreAgent: main LLM session + ReAct loop
│   ├── intent_analyzer.py        # LLM-based semantic intent classification
│   ├── tool_selector.py          # LLM-based tool selection from registry
│   ├── permission_manager.py     # Three-tier permission + risk scoring + confirmation
│   ├── execution_engine.py       # Tool execution with timeout, sandbox, capture
│   ├── response_generator.py     # Formats tool results into user response
│   ├── session_manager.py        # Manages agent session lifecycle
│   ├── context_builder.py        # Builds LLM context from memory + tools
│   ├── task_planner.py           # Analyze → Plan → Risk → Execute → Validate → Report
│   ├── self_critique.py          # Self-critique loop: generate → review → fix → deliver
│   ├── repo_analyzer.py          # Auto-detect languages, frameworks, stack, CI/CD
│   ├── context_manager.py        # Persistent project context across sessions
│   └── workflow_engine.py        # Autonomous multi-step workflow execution
│
├── agents/                       # Specialist agents
│   ├── __init__.py
│   ├── base.py                   # SpecialistAgent abstract base class
│   ├── architect_agent.py        # Structure, patterns, tech debt analysis
│   ├── developer_agent.py        # Code generation, refactoring, debugging
│   ├── security_agent.py         # Vulnerability scanning, secrets detection
│   ├── research_agent.py         # Web search, API docs, package discovery
│   ├── devops_agent.py           # Docker, CI/CD, deployment, infrastructure
│   ├── data_agent.py             # SQL, ETL, data pipelines, schema design
│   ├── qa_agent.py               # Tests, coverage, linting, validation
│   ├── fabric_agent.py           # Microsoft Fabric: lakehouses, pipelines, notebooks
│   ├── powerbi_agent.py          # Power BI: semantic models, DAX, reports
│   └── sql_agent.py              # SQL optimization, schema design, migrations
│
├── tools/
│   ├── __init__.py
│   ├── registry.py               # ToolRegistry: stores, validates, discovers, auto-registers tools
│   ├── base.py                   # BaseTool abstract class
│   │
│   ├── system/
│   │   ├── __init__.py
│   │   ├── tool.py               # SystemTool: OS info, hardware, processes
│   │   └── providers.py          # SystemProvider base + Win/Lin/Mac impl
│   │
│   ├── filesystem/
│   │   ├── __init__.py
│   │   ├── tool.py               # FSTool: read, write, search, analyze
│   │   └── providers.py          # FSProvider base + cross-platform impl
│   │
│   ├── shell/
│   │   ├── __init__.py
│   │   ├── tool.py               # ShellTool: command exec, sessions, streaming
│   │   └── providers.py          # ShellProvider base + powershell/bash/zsh impl
│   │
│   ├── git/
│   │   ├── __init__.py
│   │   └── tool.py               # GitTool: status, log, branches, PRs, analysis
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   └── tool.py               # DBTool: SQL Server, PostgreSQL, MySQL, SQLite
│   │
│   ├── network/
│   │   ├── __init__.py
│   │   ├── tool.py               # NetTool: WiFi, IP, DNS, diagnostics
│   │   └── providers.py          # NetProvider base + cross-platform impl
│   │
│   └── dev/
│       ├── __init__.py
│       └── tool.py               # DevTool: repo analysis, code review, debug
│
├── memory/
│   ├── __init__.py
│   ├── session_memory.py         # In-memory conversation + state
│   ├── project_memory.py         # Active project context (SQLite)
│   ├── long_term_memory.py       # Preferences, patterns, knowledge (SQLite + vector)
│   └── knowledge_base.py         # Index docs/, wiki/, READMEs for semantic search
│
├── permissions/
│   ├── __init__.py
│   ├── tiers.py                  # SAFE, ELEVATED, ADMIN enums + risk scoring
│   └── confirmation.py           # User confirmation prompt/flow
│
├── workflow/
│   ├── __init__.py
│   ├── engine.py                 # WorkflowEngine: execute composable multi-step workflows
│   └── definitions.py            # Built-in workflows (lint-and-fix, deploy-preview, etc.)
│
├── providers/                    # System Provider abstractions
│   ├── __init__.py
│   ├── base.py                   # AbstractSystemProvider
│   ├── windows.py                # WindowsProvider
│   ├── linux.py                  # LinuxProvider
│   └── mac.py                    # MacProvider
│
├── interfaces/
│   ├── __init__.py
│   ├── cli.py                    # Rich CLI interface
│   └── api.py                    # FastAPI REST interface
│
├── plugins/                      # Auto-discovered plugins
│   ├── __init__.py
│   ├── plugin_loader.py          # Scan directories, discover, register tools
│   └── ...
│
└── config/
    ├── __init__.py
    ├── settings.py               # Pydantic settings model
    └── tools.yaml                # Tool registry definitions
```

---

## 4. Class Design

### Core Agent

```python
class CoreAgent:
    """Main agent orchestrator. Owns the LLM session and ReAct loop."""

    def __init__(
        self,
        model_router: ModelRouter,
        tool_registry: ToolRegistry,
        permission_manager: PermissionManager,
        memory: MemoryManager,
        context_builder: ContextBuilder,
    ):
        self.model = model_router
        self.tools = tool_registry
        self.permissions = permission_manager
        self.memory = memory
        self.context = context_builder

    async def process(self, user_input: str, session_id: str) -> AgentResponse:
        """Process a single user request through the full pipeline."""
        # 1. Build context (system prompt + memory + available tools)
        context = await self.context.build(session_id, user_input)

        # 2. ReAct loop
        max_steps = 10
        for step in range(max_steps):
            # 2a. LLM reasons and selects next action
            action = await self.model.reason(context)

            if action.is_final():
                # LLM responded directly (no tool needed)
                response = self._format_response(action.content)
                await self.memory.record(session_id, user_input, response)
                return response

            # 2b. Permission check
            check = await self.permissions.check(
                action.tool_name,
                action.params,
                session_id,
            )
            if not check.allowed:
                return AgentResponse(
                    content=check.denial_message,
                    requires_confirmation=False,
                )

            # 2c. Execute tool
            result = await self.tools.execute(
                action.tool_name,
                action.params,
                timeout=check.timeout,
            )

            # 2d. Feed observation back to LLM
            context = self.context.add_observation(context, result)

        # 3. Max steps reached — synthesize final response
        return self._format_synthesis(context)
```

### Intent Analyzer

```python
class IntentAnalyzer:
    """
    LLM-based intent classification.
    No keyword lists, no regex patterns. Uses tool descriptions + examples.
    """

    async def analyze(self, user_input: str, tools: list[ToolDef]) -> IntentResult:
        prompt = f"""
        Analyze this user request and determine:
        1. The user's goal (one sentence)
        2. Which tool(s) can fulfill it
        3. Extracted parameters

        Available tools:
        {self._format_tools(tools)}

        User: {user_input}

        Respond in JSON:
        {{
            "goal": "string",
            "tools": ["tool_name"],
            "parameters": {{}},
            "confidence": 0.0-1.0,
            "requires_clarification": false
        }}
        """
        result = await self.model.chat_structured(prompt, IntentResult)
        return result

    def _format_tools(self, tools: list[ToolDef]) -> str:
        lines = []
        for t in tools:
            lines.append(f"- {t.name}: {t.description}")
            lines.append(f"  Capabilities: {', '.join(t.capabilities)}")
            lines.append(f"  Examples: {', '.join(t.examples[:3])}")
        return "\n".join(lines)
```

### Tool Base Class

```python
class BaseTool(ABC):
    """Every tool inherits from this."""

    name: str                         # Unique tool identifier
    description: str                  # LLM-facing description
    capabilities: list[str]           # What the tool can do
    permission_tier: PermissionTier   # SAFE | ELEVATED | ADMIN
    examples: list[str]               # Example queries that use this tool
    parameters: dict                  # JSON Schema for parameters

    @abstractmethod
    async def execute(self, params: dict, provider: SystemProvider) -> ToolResult:
        """Execute the tool action."""

    def get_tool_definition(self) -> dict:
        """Return OpenAI/Ollama-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self._build_llm_description(),
                "parameters": self.parameters,
            }
        }

    def _build_llm_description(self) -> str:
        """Rich description that helps LLM select this tool."""
        return (
            f"{self.description}\n\n"
            f"Capabilities: {', '.join(self.capabilities)}\n"
            f"Examples: {', '.join(self.examples)}\n"
            f"Risk: {self.permission_tier.name}"
        )
```

### Permission Manager

```python
class PermissionTier(Enum):
    SAFE = "safe"               # No confirmation needed
    ELEVATED = "elevated"       # User notified, logged
    ADMIN = "admin"             # Explicit confirmation required

class PermissionManager:
    """Three-tier permission system with confirmation flow."""

    async def check(
        self,
        tool_name: str,
        params: dict,
        session_id: str,
    ) -> PermissionCheck:
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return PermissionCheck(False, "Unknown tool")

        tier = tool.permission_tier

        # SAFE: always allowed
        if tier == PermissionTier.SAFE:
            return PermissionCheck(True, timeout=30)

        # ELEVATED: allowed but logged and user notified
        if tier == PermissionTier.ELEVATED:
            await self._notify_user(session_id, tool_name, params)
            return PermissionCheck(True, timeout=60, notify=True)

        # ADMIN: requires explicit confirmation
        if tier == PermissionTier.ADMIN:
            confirmed = await self._request_confirmation(
                session_id, tool_name, params
            )
            if confirmed:
                return PermissionCheck(True, timeout=120, confirmed=True)
            return PermissionCheck(False, "Action requires admin confirmation")

        return PermissionCheck(False, "Unknown permission tier")
```

### System Provider

```python
class SystemProvider(ABC):
    """Abstract OS operations interface. Implemented per-platform."""

    @abstractmethod
    async def get_os_info(self) -> dict: ...
    @abstractmethod
    async def get_hardware_info(self) -> dict: ...
    @abstractmethod
    async def get_cpu_info(self) -> dict: ...
    @abstractmethod
    async def get_ram_info(self) -> dict: ...
    @abstractmethod
    async def get_disk_info(self) -> list[dict]: ...
    @abstractmethod
    async def get_network_info(self) -> dict: ...
    @abstractmethod
    async def get_running_processes(self) -> list[dict]: ...
    @abstractmethod
    async def get_installed_software(self) -> list[dict]: ...
    @abstractmethod
    async def get_wifi_password(self, ssid: str | None = None) -> str: ...
    @abstractmethod
    async def get_ip_address(self) -> dict: ...
    @abstractmethod
    async def ping(self, host: str) -> dict: ...

class WindowsProvider(SystemProvider):
    """Windows implementation using PowerShell, WMIC, netsh, reg."""
    PLATFORM = "windows"

    async def get_wifi_password(self, ssid: str | None = None) -> str:
        cmd = f'netsh wlan show profile "{ssid or "*"}" key=clear'
        result = await self._run_powershell(cmd)
        return self._parse_netsh_output(result)
```

---

## 5. Tool Registry Design

```python
class ToolRegistry:
    """
    Central registry of all tools the agent can use.
    Tools are discovered, validated, and served to the LLM as function definitions.
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)

    def register(self, tool: BaseTool):
        """Register a tool with the registry."""
        self._tools[tool.name] = tool
        # Index by capability for fast lookup
        for cap in tool.capabilities:
            self._categories[cap].append(tool.name)

    def get_tool_definitions(self) -> list[dict]:
        """Return all tool definitions for LLM function calling."""
        return [t.get_tool_definition() for t in self._tools.values()]

    async def execute(self, name: str, params: dict, **kwargs) -> ToolResult:
        """Execute a named tool."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(error=f"Unknown tool: {name}")
        try:
            result = await tool.execute(params, **kwargs)
            return result
        except Exception as e:
            return ToolResult(error=str(e))
```

### Tool Definitions

```python
# tools/system/tool.py
class SystemTool(BaseTool):
    name = "system"
    description = "Retrieves operating system and hardware information."
    capabilities = [
        "get_os_info", "get_hardware_info", "get_cpu_info",
        "get_ram_info", "get_disk_info", "get_network_info",
        "get_running_processes", "get_installed_software",
    ]
    permission_tier = PermissionTier.SAFE
    examples = [
        "What OS am I running?",
        "Show me my hardware specs",
        "How much RAM do I have?",
        "List running processes",
        "What software is installed?",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "enum": ["os", "hardware", "cpu", "ram", "disk",
                         "network", "processes", "software", "all"],
                "description": "What system information to retrieve",
            }
        },
        "required": ["query"],
    }

# tools/network/tool.py
class NetworkTool(BaseTool):
    name = "network"
    description = "Retrieves network configuration, WiFi details, and performs diagnostics."
    capabilities = [
        "get_wifi_password", "get_ip_address", "get_dns_info",
        "ping", "traceroute", "get_network_adapters",
    ]
    permission_tier = PermissionTier.ELEVATED
    examples = [
        "What is my WiFi password?",
        "Show my wireless key",
        "What is my IP address?",
        "Ping google.com",
        "Show DNS configuration",
        "What network am I connected to?",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["wifi_password", "ip_address", "dns",
                         "ping", "traceroute", "adapters", "info"],
            },
            "target": {
                "type": "string",
                "description": "SSID for WiFi or host for ping",
            },
        },
        "required": ["action"],
    }

# tools/shell/tool.py
class ShellTool(BaseTool):
    name = "shell"
    description = "Executes terminal commands with output capture and session management."
    capabilities = [
        "run_command", "stream_command", "manage_session",
    ]
    permission_tier = PermissionTier.ADMIN
    examples = [
        "Run 'dir' in my project folder",
        "Execute pytest tests/",
        "Show disk usage",
        "List all environment variables",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "workdir": {"type": "string", "description": "Working directory"},
            "timeout": {"type": "integer", "description": "Timeout in seconds"},
            "stream": {"type": "boolean", "description": "Stream output in real-time"},
        },
        "required": ["command"],
    }

# tools/filesystem/tool.py
class FileSystemTool(BaseTool):
    name = "filesystem"
    description = "Reads, writes, searches, and manages files within allowed boundaries."
    capabilities = [
        "read_file", "write_file", "search_files",
        "analyze_repository", "create_file", "rename_file", "move_file",
    ]
    permission_tier = PermissionTier.ELEVATED  # read is SAFE, write is ADMIN
    examples = [
        "Read src/main.py",
        "Create a new file at config/settings.json",
        "Search for files containing 'api_key'",
        "Analyze the project structure",
    ]
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "search", "analyze",
                         "create", "rename", "move", "delete"],
            },
            "path": {"type": "string"},
            "content": {"type": "string"},
            "pattern": {"type": "string"},
        },
        "required": ["action", "path"],
    }

    async def execute(self, params: dict, provider: SystemProvider) -> ToolResult:
        action = params["action"]
        path = params["path"]

        if action in ("read", "search", "analyze"):
            permission_tier = PermissionTier.SAFE  # Read operations are safe
        else:
            permission_tier = PermissionTier.ADMIN  # Write operations need confirmation

        return await super().execute(params, provider)
```

### Complete Tool Inventory

| Tool | Capabilities | Tier | Examples |
|------|-------------|------|----------|
| `system` | OS, hardware, CPU, RAM, disk, network, processes, software | SAFE | "What OS?", "Show specs" |
| `filesystem` | Read, write, search, analyze, create, rename, move | SAFE/ADMIN | "Read file", "Create project" |
| `shell` | Run command, stream, session mgmt | ADMIN | "Run tests", "Show disk" |
| `git` | Status, log, branches, diff, PR, analyze | ELEVATED | "Git status", "Show branches" |
| `database` | Query SQL Server, PostgreSQL, MySQL, SQLite | ADMIN | "Select users", "Show tables" |
| `network` | WiFi, IP, DNS, ping, traceroute, adapters | ELEVATED | "WiFi password", "Ping host" |
| `dev` | Repo analysis, code review, debug, architecture | SAFE | "Review this code", "Analyze repo" |

---

## 6. Permission System

### Three-Tier Model

```
┌─────────────────────────────────────────────────────────────┐
│                    PERMISSION TIERS                           │
│                                                              │
│  SAFE ─────────────────────────────────────────────────────  │
│  • Read system information                                   │
│  • Read files (existing paths)                               │
│  • Search files                                              │
│  • Analyze repositories                                      │
│  • Git status/log/branch (read operations)                   │
│  • Code review / analysis                                    │
│  → No confirmation required                                  │
│  → Logged to audit trail                                     │
│  → 30s timeout                                               │
│                                                              │
│  ELEVATED ─────────────────────────────────────────────────  │
│  • Read WiFi passwords                                       │
│  • Read process details                                      │
│  • Network diagnostics                                       │
│  • Read database schema                                      │
│  • Git push/pull (non-destructive mutations)                 │
│  → User notified via status bar                              │
│  → Logged to audit trail                                     │
│  → 60s timeout                                               │
│  → Can be opted-out by user setting                          │
│                                                              │
│  ADMIN ────────────────────────────────────────────────────  │
│  • Modify/create/delete files                                │
│  • Execute terminal commands                                 │
│  • Install/uninstall software                                │
│  • Kill processes                                            │
│  • Modify system configuration                               │
│  • Database write operations                                 │
│  → Explicit user confirmation required                       │
│  → Confirmation shows: tool name, params, risk summary       │
│  → Logged to audit trail with user response                  │
│  → 120s timeout                                              │
│  → User can reject or approve                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Confirmation Flow

```
User asks: "Remove the logs directory and all its contents"

1. Intent Analysis → FileSystemTool(delete)
2. Permission Check → ADMIN tier → confirmation required
3. UI shows:
   ┌─────────────────────────────────────────────────────┐
   │  ⚠ ADMIN ACTION REQUIRED                             │
   │                                                     │
   │  Tool:    FileSystemTool                             │
   │  Action:  delete                                    │
   │  Target:  /home/user/project/logs/                  │
   │  Risk:    This will permanently remove 12 files      │
   │                                                     │
   │  [y] Approve  [n] Reject  [s] Show details          │
   └─────────────────────────────────────────────────────┘
4. User approves → Execute with audit trail
5. User rejects → Return denial response to LLM → LLM tries alternative
```

### Dynamic Tier Adjustment

Some tools adjust their permission tier based on parameters:

```python
class FileSystemTool(BaseTool):
    async def get_permission_tier(self, params: dict) -> PermissionTier:
        action = params.get("action", "")
        if action in ("read", "search", "analyze"):
            return PermissionTier.SAFE
        elif action in ("rename", "move"):
            return PermissionTier.ELEVATED
        else:  # write, create, delete
            return PermissionTier.ADMIN
```

---

## 7. Memory System

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          MEMORY SYSTEM                               │
│                                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────┐│
│  │  SESSION MEMORY      │  │  PROJECT MEMORY      │  │ LONG-TERM   ││
│  │  (In-Memory)         │  │  (SQLite)            │  │ (SQLite +   ││
│  ├─────────────────────┤  ├─────────────────────┤  │  Vector DB)  ││
│  │ • Conversation turn  │  │ • Active repo path   │  ├──────────────┤│
│  │ • Last N messages    │  │ • Language/stack     │  │ • User       ││
│  │ • Current state      │  │ • Open issues        │  │   preferences││
│  │ • Pending actions    │  │ • Decisions made     │  │ • Learned    ││
│  │ • Tool history       │  │ • Current task       │  │   patterns   ││
│  │                      │  │ • Previous actions    │  │ • Tool usage ││
│  │ Max: 50 turns        │  │                      │  │   history    ││
│  │ TTL: session end     │  │ Persisted: forever   │  │ • Security   ││
│  └─────────────────────┘  └─────────────────────┘  │   baseline   ││
│                                                     └──────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### Memory Classes

```python
class SessionMemory:
    """In-memory conversation and state for the current session."""

    def __init__(self, max_turns: int = 50):
        self.turns: list[Turn] = []
        self.max_turns = max_turns
        self.state: dict = {}
        self.pending_actions: list[PendingAction] = []

    def add_turn(self, user: str, assistant: str, tool_calls: list = None):
        self.turns.append(Turn(user, assistant, tool_calls))
        if len(self.turns) > self.max_turns:
            self.turns.pop(0)  # Summarize old turns instead in production

    def get_context(self, token_limit: int = 4096) -> list[dict]:
        """Return messages in LLM format, truncated to token limit."""
        messages = []
        total = 0
        for turn in reversed(self.turns):
            msgs = turn.to_messages()
            tokens = count_tokens(msgs)
            if total + tokens > token_limit:
                break
            messages = msgs + messages
            total += tokens
        return messages


class ProjectMemory:
    """Persistent project context stored in SQLite."""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_db()

    def set_active_project(self, path: str):
        """Record the currently active project."""
        info = self._detect_project_info(path)
        self.db.execute("""
            INSERT OR REPLACE INTO active_project
            (path, name, language, framework, detected_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (path, info.name, info.language, info.framework))

    def get_active_project(self) -> ProjectInfo | None:
        row = self.db.execute("""
            SELECT path, name, language, framework
            FROM active_project
            ORDER BY detected_at DESC LIMIT 1
        """).fetchone()
        if row:
            return ProjectInfo(*row)
        return None

    def record_decision(self, topic: str, decision: str, reasoning: str):
        """Store architectural decisions for context continuity."""
        self.db.execute("""
            INSERT INTO decisions (topic, decision, reasoning, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (topic, decision, reasoning))

    def get_recent_decisions(self, limit: int = 5) -> list[dict]:
        return self.db.execute("""
            SELECT topic, decision, reasoning, created_at
            FROM decisions ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()


class LongTermMemory:
    """User preferences, learned patterns, and knowledge base."""

    def __init__(self, db_path: str, embedding_model: str = "local"):
        self.db = sqlite3.connect(db_path)
        self.embeddings = EmbeddingModel(embedding_model)

    async def remember_preference(self, key: str, value: str):
        """Store a user preference (e.g., 'python_style' -> 'black')."""
        self.db.execute("""
            INSERT OR REPLACE INTO preferences (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (key, value))

    async def get_preference(self, key: str) -> str | None:
        row = self.db.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    async def learn_pattern(self, context: str, action: str, success: bool):
        """Learn a tool usage pattern from successful interactions."""
        embedding = await self.embeddings.embed(context)
        self.db.execute("""
            INSERT INTO learned_patterns (context, action, success, embedding, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        """, (context, action, success, embedding.tobytes()))

    async def recall_similar_pattern(self, context: str) -> list[dict]:
        """Find similar contexts where patterns were learned."""
        embedding = await self.embeddings.embed(context)
        # Cosine similarity search (simplified — use vector DB in production)
        rows = self.db.execute("""
            SELECT context, action, success, embedding
            FROM learned_patterns
            WHERE success = 1
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
        return [
            {"context": r[0], "action": r[1]}
            for r in rows
            if self._cosine_similarity(embedding, r[3]) > 0.85
        ]
```

---

## 8. Intent Analysis Workflow

### Sematic Intent Understanding (Not Keyword Routing)

```
User Input: "what is my WiFi password"

Step 1: Intent Analyzer receives input + all tool definitions

Step 2: LLM classifies:
  {
    "goal": "Retrieve the Wi-Fi password for the currently connected network",
    "tools": ["network"],
    "parameters": {"action": "wifi_password"},
    "confidence": 0.97,
    "requires_clarification": false
  }

Step 3: Tool Selector confirms tool choice

Step 4: Permission check → ELEVATED → user notified

Step 5: Execute → retruns result

Step 6: Response Generator formats:
  ```
  ✓ Network Information

    Connected SSID: "HomeNetwork-5G"
    Password:       MySecurePass123
    Security:       WPA2-Personal
  ```
```

### Intent Classification Prompt

```python
class IntentAnalyzer:
    ANALYZE_PROMPT = """
    You are an intent analysis system for a local AI assistant.

    Your job: analyze the user's request and determine which tool(s) can fulfill it.

    Rules:
    - Do NOT match keywords — understand the semantic meaning
    - Multiple phrasings should map to the same tool
    - If uncertain, return requires_clarification: true
    - Extract structured parameters from natural language

    Examples of semantic equivalence:
    - "What is my WiFi password?" → network tool, wifi_password action
    - "Show my wireless key" → network tool, wifi_password action
    - "What credentials is my PC using?" → network tool, wifi_password action
    - "How much RAM do I have?" → system tool, ram action
    - "Show my computer specs" → system tool, hardware action
    - "List all processes" → system tool, processes action
    - "Read the README.md file" → filesystem tool, read action

    Available tools and their capabilities:
    {tool_descriptions}

    User request: {user_input}

    Respond in JSON format with: goal, tools[], parameters{}, confidence, requires_clarification
    """
```

---

## 9. Tool Selection Workflow

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  INTENT ANALYZER                                             │
│  • LLM classifies intent from tool descriptions             │
│  • Output: intent with tool candidates + params             │
│  • Confidence score                                         │
│                                                             │
│  Confidence < 0.6 ───→ Ask user for clarification           │
│  Confidence ≥ 0.6 ───→ Continue to Tool Selector           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  TOOL SELECTOR                                               │
│  • LLM reviews tool definitions (name, desc, caps, ex)      │
│  • Verifies: is this the right tool for this intent?        │
│  • Can chain multiple tools if needed                       │
│                                                             │
│  Single tool ───→ Execute directly                          │
│  Multi-tool ────→ Build execution plan                      │
│  No match ──────→ Return "I can't do that" + suggest alt    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  PERMISSION CHECK                                            │
│  • SAFE: no confirmation                                    │
│  • ELEVATED: notify user                                    │
│  • ADMIN: request confirmation                              │
│                                                             │
│  Allowed ──────→ Execute                                     │
│  Denied ───────→ Return denial + reason to LLM               │
│  Pending ──────→ Wait for user confirmation                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  EXECUTION + OBSERVATION                                     │
│  • Execute tool with timeout                                 │
│  • Capture output, errors, warnings                          │
│  • Feed result back to LLM as observation                   │
│                                                             │
│  Success ────→ LLM decides: done or next step?              │
│  Error ──────→ LLM retries or tries alternative              │
│  Timeout ────→ LLM adjusts approach                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  RESPONSE GENERATION                                         │
│  • LLM synthesizes final response from all observations      │
│  • Self-validates: correctness, security, completeness       │
│  • Formats with structured sections / symbols                │
│  • Returns to user                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Python Implementation Examples

### Tool Registration

```python
# tools/registry.py
from viki.v2.tools.system.tool import SystemTool
from viki.v2.tools.filesystem.tool import FileSystemTool
from viki.v2.tools.shell.tool import ShellTool
from viki.v2.tools.git.tool import GitTool
from viki.v2.tools.database.tool import DatabaseTool
from viki.v2.tools.network.tool import NetworkTool
from viki.v2.tools.dev.tool import DevTool

def create_tool_registry(provider: SystemProvider) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SystemTool(provider))
    registry.register(FileSystemTool(provider))
    registry.register(ShellTool(provider))
    registry.register(GitTool(provider))
    registry.register(DatabaseTool(provider))
    registry.register(NetworkTool(provider))
    registry.register(DevTool(provider))
    return registry
```

### System Tool with Cross-Platform Provider

```python
# tools/system/tool.py
class SystemTool(BaseTool):
    def __init__(self, provider: SystemProvider):
        self.provider = provider
        super().__init__()

    async def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "all")
        try:
            if query == "os":
                data = await self.provider.get_os_info()
            elif query == "hardware":
                data = await self.provider.get_hardware_info()
            elif query == "cpu":
                data = await self.provider.get_cpu_info()
            elif query == "ram":
                data = await self.provider.get_ram_info()
            elif query == "disk":
                data = await self.provider.get_disk_info()
            elif query == "network":
                data = await self.provider.get_network_info()
            elif query == "processes":
                data = await self.provider.get_running_processes()
            elif query == "software":
                data = await self.provider.get_installed_software()
            else:
                data = {
                    "os": await self.provider.get_os_info(),
                    "hardware": await self.provider.get_hardware_info(),
                    "ram": await self.provider.get_ram_info(),
                    "disk": await self.provider.get_disk_info(),
                }
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
```

### Provider Factory

```python
# providers/__init__.py
import sys

def create_provider() -> SystemProvider:
    """Factory: returns the correct provider for the current platform."""
    platform = sys.platform.lower()
    if platform == "win32":
        from viki.v2.providers.windows import WindowsProvider
        return WindowsProvider()
    elif platform == "linux":
        from viki.v2.providers.linux import LinuxProvider
        return LinuxProvider()
    elif platform == "darwin":
        from viki.v2.providers.mac import MacProvider
        return MacProvider()
    raise RuntimeError(f"Unsupported platform: {platform}")
```

### Windows WiFi Password Provider

```python
# providers/windows.py
class WindowsProvider(SystemProvider):
    """Windows implementation using PowerShell commands."""

    def __init__(self):
        self.PLATFORM = "windows"

    async def _run_powershell(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("cp1252", errors="replace"))
        return stdout.decode("cp1252", errors="replace")

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        if not ssid:
            # Get current SSID
            out = await self._run_powershell(
                "(netsh wlan show interfaces | Select-String 'SSID' | "
                "Select-String -NotMatch 'BSSID' | "
                "ForEach-Object { $_ -replace '.*:\\s+', '' }).Trim()"
            )
            ssid = out.strip()
        if not ssid:
            return {"error": "Not connected to any Wi-Fi network"}

        out = await self._run_powershell(
            f'netsh wlan show profile name="{ssid}" key=clear'
        )
        password = ""
        for line in out.splitlines():
            if "Key Content" in line:
                password = line.split(":")[-1].strip()
                break

        return {
            "ssid": ssid.strip(),
            "password": password or "No password (open network)",
            "key": password or "none",
        }

    async def get_os_info(self) -> dict:
        out = await self._run_powershell(
            "Get-ComputerInfo | Select-Object WindowsVersion, "
            "WindowsEditionId, WindowsInstallationType, OsName, OsVersion | ConvertTo-Json"
        )
        return json.loads(out)
```

### Linux WiFi Password Provider

```python
# providers/linux.py
class LinuxProvider(SystemProvider):
    """Linux implementation using nmcli, iw, and /proc/sysfs."""

    async def _run_bash(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode())
        return stdout.decode()

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        if not ssid:
            out = await self._run_bash(
                "iwgetid -r 2>/dev/null || nmcli -t -f ACTIVE,SSID dev wifi "
                "| grep '^yes' | cut -d: -f2"
            )
            ssid = out.strip()
        if not ssid:
            return {"error": "Not connected to any Wi-Fi network"}

        try:
            out = await self._run_bash(
                f'nmcli -s -g 802-11-wireless-security.psk connection show "{ssid}"'
            )
            password = out.strip()
        except RuntimeError:
            try:
                out = await self._run_bash(
                    f"sudo cat /etc/NetworkManager/system-connections/"
                    f'"{ssid}.nmconnection" 2>/dev/null | grep psk='
                )
                password = out.replace("psk=", "").strip()
            except RuntimeError:
                password = ""

        return {
            "ssid": ssid,
            "password": password or "Requires sudo or NetworkManager",
        }

    async def get_os_info(self) -> dict:
        out = await self._run_bash(
            "cat /etc/os-release | grep -E '^(NAME|VERSION|ID)=' | "
            "sort | head -3 && uname -a"
        )
        lines = out.strip().splitlines()
        info = {}
        for line in lines:
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.lower()] = v.strip('"')
        return info
```

### Mac WiFi Password Provider

```python
# providers/mac.py
class MacProvider(SystemProvider):
    """macOS implementation using networksetup, system_profiler, scutil."""

    async def _run_zsh(self, command: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "zsh", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode())
        return stdout.decode()

    async def get_wifi_password(self, ssid: str | None = None) -> dict:
        if not ssid:
            out = await self._run_zsh("/System/Library/PrivateFrameworks/"
                "Apple80211.framework/Versions/Current/Resources/airport -I "
                "| awk '/ SSID:/ {print $2}'"
            )
            ssid = out.strip()
        if not ssid:
            return {"error": "Not connected to any Wi-Fi network"}

        out = await self._run_zsh(
            f'security find-generic-password -D "AirPort network password" '
            f'-a "{ssid}" -w 2>/dev/null'
        )
        password = out.strip() if out.strip() else "Requires sudo or Keychain unlock"

        return {
            "ssid": ssid,
            "password": password,
        }
```

---

## 11. Cross-Platform Strategy

### Provider Abstract Base

```python
class SystemProvider(ABC):
    """Every OS interaction goes through this interface."""

    # ── System Inspection ──
    @abstractmethod
    async def get_os_info(self) -> dict: ...
    @abstractmethod
    async def get_hardware_info(self) -> dict: ...
    @abstractmethod
    async def get_cpu_info(self) -> dict: ...
    @abstractmethod
    async def get_ram_info(self) -> dict: ...
    @abstractmethod
    async def get_disk_info(self) -> list[dict]: ...
    @abstractmethod
    async def get_running_processes(self) -> list[dict]: ...
    @abstractmethod
    async def get_installed_software(self) -> list[dict]: ...

    # ── Network ──
    @abstractmethod
    async def get_wifi_password(self, ssid: str | None = None) -> dict: ...
    @abstractmethod
    async def get_ip_address(self) -> dict: ...
    @abstractmethod
    async def get_dns_info(self) -> dict: ...
    @abstractmethod
    async def ping(self, host: str) -> dict: ...

    # ── Filesystem ──
    @abstractmethod
    async def read_file(self, path: str) -> str: ...
    @abstractmethod
    async def write_file(self, path: str, content: str) -> bool: ...
    @abstractmethod
    async def search_files(self, root: str, pattern: str) -> list[str]: ...

    # ── Shell ──
    @abstractmethod
    async def run_command(self, command: str, workdir: str | None = None) -> ShellResult: ...
```

### Platform Detection

```python
def detect_platform() -> Platform:
    """Return the current platform enum."""
    p = sys.platform.lower()
    if p == "win32":
        return Platform.WINDOWS
    elif p == "linux":
        return Platform.LINUX
    elif p == "darwin":
        return Platform.MAC
    else:
        raise UnsupportedPlatformError(p)

def create_provider(platform: Platform | None = None) -> SystemProvider:
    """Factory method for cross-platform provider creation."""
    platform = platform or detect_platform()
    providers = {
        Platform.WINDOWS: WindowsProvider,
        Platform.LINUX: LinuxProvider,
        Platform.MAC: MacProvider,
    }
    cls = providers.get(platform)
    if not cls:
        raise UnsupportedPlatformError(platform)
    return cls()
```

### Cross-Platform Decision Matrix

| Capability | Windows | Linux | macOS |
|-----------|---------|-------|-------|
| OS info | `Get-ComputerInfo` | `/etc/os-release` + `uname` | `sw_vers` + `system_profiler` |
| CPU info | `Get-CimInstance Win32_Processor` | `/proc/cpuinfo` | `sysctl -n machdep.cpu` |
| RAM info | `Get-CimInstance Win32_ComputerSystem` | `/proc/meminfo` | `sysctl -n hw.memsize` |
| Disk info | `Get-CimInstance Win32_LogicalDisk` | `df -h` | `df -h` |
| Running processes | `Get-Process` | `ps aux` | `ps aux` |
| Installed software | `Get-ItemProperty HKLM:\Software\...` | `dpkg -l` / `rpm -qa` | `system_profiler SPApplicationsDataType` |
| WiFi password | `netsh wlan show profile key=clear` | `nmcli connection show` | `security find-generic-password` |
| IP address | `Get-NetIPAddress` | `ip addr show` | `ifconfig` / `ipconfig` |
| DNS info | `Get-DnsClientServerAddress` | `resolvectl status` | `scutil --dns` |
| Ping | `Test-Connection` | `ping -c 4` | `ping -c 4` |
| File read/write | Built-in `open()` | Built-in `open()` | Built-in `open()` |
| Shell execution | `powershell -Command` | `bash -c` | `zsh -c` |

---

## 12. Error Handling Strategy

### Error Taxonomy

```python
class ToolError(Enum):
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    INVALID_PARAMS = "invalid_parameters"
    EXECUTION_FAILED = "execution_failed"
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    NOT_FOUND = "not_found"
    PROVIDER_ERROR = "provider_error"
    RATE_LIMITED = "rate_limited"

class ToolResult:
    """Standardized return type for every tool execution."""

    def __init__(
        self,
        success: bool,
        data: Any = None,
        error: str | None = None,
        error_type: ToolError | None = None,
        warnings: list[str] = None,
    ):
        self.success = success
        self.data = data
        self.error = error
        self.error_type = error_type
        self.warnings = warnings or []

    def to_llm_observation(self) -> str:
        """Format the result for LLM consumption in the ReAct loop."""
        if self.success:
            result_str = json.dumps(self.data, indent=2, default=str)
            warnings_str = ""
            if self.warnings:
                warnings_str = f"\nWarnings:\n" + "\n".join(f"  - {w}" for w in self.warnings)
            return f"Tool succeeded.\nResult:\n{result_str}{warnings_str}"
        else:
            return f"Tool failed: [{self.error_type.value}] {self.error}"
```

### Error Handling Flow

```
Tool Execution Error
    │
    ├── PERMISSION_DENIED ─────→ Return to LLM → LLM tries alternative approach
    │                              or requests user approval
    │
    ├── TIMEOUT ───────────────→ Return partial result if available
    │                              LLM retries with smaller scope
    │
    ├── INVALID_PARAMS ────────→ LLM reformulates parameters and retries
    │
    ├── EXECUTION_FAILED ──────→ LLM diagnoses error, tries alternative
    │                              If 3 consecutive failures → circuit breaker
    │
    ├── UNSUPPORTED_PLATFORM ──→ Return clear message to user
    │                              Suggest alternative approach
    │
    ├── NOT_FOUND ─────────────→ Return to LLM → suggests similar alternatives
    │
    └── PROVIDER_ERROR ────────→ Log error, return to LLM
                                   If provider unavailable → degrade gracefully
```

### Circuit Breaker

```python
class CircuitBreaker:
    """Prevents cascading failures by stopping repeated calls to failing tools."""

    def __init__(self, threshold: int = 3, cooldown: int = 60):
        self.failures: dict[str, int] = {}
        self.last_failure: dict[str, float] = {}
        self.threshold = threshold
        self.cooldown = cooldown

    async def call(self, tool_name: str, fn: Callable) -> ToolResult:
        now = time.time()

        # Check if circuit is open
        if tool_name in self.last_failure:
            elapsed = now - self.last_failure[tool_name]
            if elapsed < self.cooldown and self.failures.get(tool_name, 0) >= self.threshold:
                return ToolResult(
                    success=False,
                    error=f"Tool '{tool_name}' temporarily unavailable "
                          f"({self.cooldown - elapsed:.0f}s cooldown remaining)",
                    error_type=ToolError.RATE_LIMITED,
                )

        # Execute with circuit tracking
        result = await fn()

        if not result.success and result.error_type in (
            ToolError.TIMEOUT, ToolError.EXECUTION_FAILED, ToolError.PROVIDER_ERROR
        ):
            self.failures[tool_name] = self.failures.get(tool_name, 0) + 1
            self.last_failure[tool_name] = now
        else:
            self.failures[tool_name] = 0

        return result
```

---

## 13. Security Recommendations

### Principle of Least Privilege

```
┌──────────────────────────────────────────────────────────────┐
│  TOOL PERMISSION MATRIX                                       │
│                                                              │
│  SAFE:      Read system info, read files, search, analyze    │
│  ELEVATED:  WiFi passwords, process details, network diag    │
│  ADMIN:     Write files, shell commands, DB writes,          │
│             kill processes, install software                 │
│                                                              │
│  Default:   All tools start at their documented tier          │
│  User:      Can elevate or restrict tiers in config           │
│  Session:   Can temporarily approve ADMIN actions            │
└──────────────────────────────────────────────────────────────┘
```

### Sandboxing

```python
class PathSandbox:
    """Prevents filesystem access outside allowed directories."""

    ALLOWED_ROOTS = {
        "win32": [
            os.path.expanduser("~"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Desktop"),
            os.getcwd(),
        ],
        "linux": [
            os.path.expanduser("~"),
            os.getcwd(),
        ],
        "darwin": [
            os.path.expanduser("~"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Desktop"),
            os.getcwd(),
        ],
    }

    BLOCKED_PATHS = {
        "win32": [
            r"C:\Windows", r"C:\Windows\System32", r"C:\Program Files",
            r"C:\Program Files (x86)", r"C:\Boot",
        ],
        "linux": [
            "/etc", "/usr", "/bin", "/sbin", "/boot",
            "/sys", "/proc", "/dev", "/root",
        ],
        "darwin": [
            "/etc", "/usr", "/bin", "/sbin", "/System",
            "/Library", "/var/root",
        ],
    }

    @classmethod
    def validate_path(cls, path: str) -> bool:
        real = os.path.realpath(path)
        platform = sys.platform.lower()
        for blocked in cls.BLOCKED_PATHS.get(platform, []):
            if real.startswith(os.path.realpath(blocked)):
                return False
        return True
```

### Shell Command Safety

```python
class ShellSafety:
    """Validates and classifies shell commands before execution."""

    BLOCKED_PATTERNS = [
        r"rm\s+(-rf\s+)?/",           # rm -rf /
        r"format\s+\w:",               # format C:
        r"dd\s+if=.*of=/dev/",         # dd destructive
        r":\(\)\s*\{.*:\(\)\s*;\};",    # Fork bomb
        r"chmod\s+-R\s*777\s*/",       # chmod entire FS
    ]

    DESTRUCTIVE_PATTERNS = [
        r"rm\s+-rf",                    # Force recursive delete
        r"del\s+/[FQS]",                # Force delete Windows
        r"format\b",
        r"shutdown\s+.*/t\s+0",         # Immediate shutdown
        r"taskkill\s+/F",              # Force kill
    ]

    @classmethod
    def classify(cls, command: str) -> CommandTier:
        """Classify a command's safety tier."""
        for pattern in cls.BLOCKED_PATTERNS:
            if re.search(pattern, command):
                return CommandTier.FORBIDDEN
        for pattern in cls.DESTRUCTIVE_PATTERNS:
            if re.search(pattern, command):
                return CommandTier.DESTRUCTIVE
        return CommandTier.SAFE
```

### Audit Trail

```python
class AuditTrail:
    """Immutable log of every tool execution for security review."""

    def __init__(self, db_path: str):
        self.db = sqlite3.connect(db_path)
        self._init_db()

    def record(
        self,
        session_id: str,
        tool: str,
        params: dict,
        tier: PermissionTier,
        approved: bool,
        result: ToolResult,
    ):
        self.db.execute("""
            INSERT INTO audit_log
            (session_id, tool, params, tier, approved, success, error, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            session_id, tool, json.dumps(params), tier.value,
            approved, result.success, result.error,
        ))
```

---

## 14. Scalability Recommendations & Long-Term Vision

### Multi-Session Architecture

```python
class AgentSessionManager:
    """Manages multiple concurrent agent sessions."""

    def __init__(self, tool_registry: ToolRegistry, model_router: ModelRouter):
        self.sessions: dict[str, AgentSession] = {}
        self.tools = tool_registry
        self.model = model_router

    async def get_or_create(self, session_id: str) -> AgentSession:
        if session_id not in self.sessions:
            self.sessions[session_id] = AgentSession(
                session_id=session_id,
                tool_registry=self.tools,
                model_router=self.model,
                memory=SessionMemory(),
            )
        return self.sessions[session_id]
```

### Scalability Matrix

| Dimension | Recommendation |
|-----------|---------------|
| **Session count** | 1 agent session per user. Sessions are lightweight (in-memory state, lazy DB) |
| **Memory** | SQLite handles thousands of concurrent reads. For >100 users, swap to PostgreSQL |
| **Embeddings** | Local sentence-transformers (CPU, ~50ms). For >1K concurrent, move to REST embedding service |
| **LLM calls** | Ollama handles 1-4 concurrent requests per model. Use model routing to distribute load |
| **Plugin isolation** | Each plugin runs in its own subprocess with IPC. Plugin crash doesn't bring down the agent |
| **Cross-session context** | ProjectMemory and LongTermMemory are thread-safe SQLite. Future: PostgreSQL with pgvector |
| **Tool caching** | ToolCache for SAFE-tier results eliminates redundant OS calls within TTL window |

### Long-Term Vision: Full Agent Platform

As VIKI matures, the architecture evolves from an agent to an **agent platform** — a multi-agent, plugin-extensible operating system for developer machines.

```
VIKI Core
│
├── LLM Router              →  Routes to specialist models (fast vs deep vs code)
├── Agent Manager           →  Spawns, monitors, and kills specialist agents
├── Memory Manager          →  Session + Project + Long-Term + Knowledge Base
├── Tool Registry           →  Core tools + auto-discovered + plugin tools
├── Permission Manager      →  SAFE / ELEVATED / ADMIN + risk scoring
├── Workflow Engine         →  Analyze → Plan → Risk → Execute → Validate → Report
│
├── Architect Agent         →  System design, architecture review, dependency analysis
├── Developer Agent         →  Code generation, refactoring, debugging
├── Security Agent          →  Vulnerability scanning, secret detection, dependency audit
├── Research Agent          →  Web search, documentation lookup, API discovery
├── DevOps Agent            →  Docker, CI/CD, deployment, infrastructure
├── Data Agent              →  Database queries, data pipelines, ETL
├── QA Agent                →  Test generation, test execution, coverage analysis
│
├── Filesystem Tool         →  Read/write/search files, directory operations
├── Git Tool                →  Clone, commit, branch, diff, log
├── Terminal Tool           →  Run commands, capture output, stream long-running
├── Database Tool           →  SQL queries, schema inspection, data export
├── Browser Tool            →  Web fetch, form submission, screenshot
├── Memory Tool             →  Store/recall preferences, patterns, decisions
│
└── Plugin Ecosystem
    ├── Jira Plugin         →  Tickets, sprints, board management
    ├── GitHub Plugin       →  PRs, issues, actions, releases
    ├── Fabric Plugin       →  Lakehouses, warehouses, pipelines, notebooks
    ├── Power BI Plugin     →  Semantic models, DAX, reports, datasets
    ├── Azure Plugin        →  Resources, cost analysis, deployment
    └── Docker Plugin       →  Containers, images, compose, registries
```

This architecture transforms VIKI from a **chatbot with a large prompt** into a **true agent platform** — where the most impactful upgrades come from tool orchestration, memory, planning, and specialized agents rather than prompt engineering.

### Key Architectural Principles for the Future

1. **Agents are stateless** — all state lives in Memory Manager. Agents can be killed and respawned
2. **Tools are discoverable** — plugins register themselves. No manual wiring
3. **Workflows are composable** — complex tasks are built from simple steps. Each step is a tool call
4. **Risk is quantifiable** — every action has a risk score. HIGH requires confirmation
5. **Memory is hierarchical** — session (volatile) → project (persistent) → knowledge (indexed)
6. **LLM is swappable** — model routing allows per-agent specialization without code changes

### Plugin System for Tools

```python
class ToolPlugin:
    """Third-party tool plugin. Register via config or discovery."""

    @abstractmethod
    def register(self, registry: ToolRegistry): ...
    @abstractmethod
    def get_provider_dependencies(self) -> list[type]: ...

class PluginLoader:
    """Discovers and loads tool plugins from configured paths."""

    def load(self, plugin_dirs: list[str], registry: ToolRegistry):
        for dir_path in plugin_dirs:
            for file in Path(dir_path).glob("*_tool.py"):
                spec = importlib.util.spec_from_file_location(file.stem, file)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for attr in dir(mod):
                    cls = getattr(mod, attr)
                    if isinstance(cls, type) and issubclass(cls, ToolPlugin):
                        cls().register(registry)
```

### Performance Optimizations

```python
class ToolCache:
    """Caches SAFE-tier tool results with TTL."""

    def __init__(self, ttl: int = 60):
        self.cache: dict[str, tuple[float, ToolResult]] = {}
        self.ttl = ttl

    async def get_or_compute(
        self, key: str, fn: Callable, tier: PermissionTier
    ) -> ToolResult:
        if tier == PermissionTier.SAFE and key in self.cache:
            cached_at, result = self.cache[key]
            if time.time() - cached_at < self.ttl:
                return result
        result = await fn()
        if tier == PermissionTier.SAFE and result.success:
            self.cache[key] = (time.time(), result)
        return result
```

---

## 15. Multi-Agent System

Instead of a single monolithic agent, VIKI v2 routes tasks to **specialist agents** that each focus on one domain.

### Agent Architecture

```
User Request
     │
     ▼
VIKI Core (Dispatcher)
     │
     ├──→ Architect Agent    —  Structure, patterns, dependencies, tech debt
     ├──→ Developer Agent    —  Code generation, refactoring, debugging
     ├──→ Security Agent     —  Vulnerability scan, secrets, dependency audit
     ├──→ Research Agent     —  Web search, API docs, package discovery
     ├──→ DevOps Agent       —  Docker, CI/CD pipelines, infrastructure
     ├──→ Data Agent         —  SQL, ETL, data pipelines, schema design
     └──→ QA Agent           —  Tests, coverage, linting, validation
          │
          ▼
     Final consolidated report
```

### Agent Interface

```python
class SpecialistAgent(ABC):
    name: str
    description: str
    domain: str

    @abstractmethod
    async def analyze(self, context: dict) -> AgentFindings: ...

    @abstractmethod
    async def execute(self, plan: ActionPlan) -> AgentResult: ...

@dataclass
class AgentFindings:
    summary: str
    confidence: float
    risks: list[str]
    recommendations: list[str]

@dataclass
class AgentResult:
    success: bool
    output: str
    artifacts: list[str]
```

### Example: Repository Review

```
User: "Review this repository."

VIKI Core dispatches to all agents in parallel:

┌─ Architect Agent ─────────────────────────────────────────────┐
│ • Detects: React frontend, FastAPI backend, SQLite database    │
│ • Issues: No service layer, controllers are fat                │
│ • Score: 6/10                                                  │
└────────────────────────────────────────────────────────────────┘

┌─ Security Agent ───────────────────────────────────────────────┐
│ • Found: 3 hardcoded secrets, 2 outdated dependencies          │
│ • Risk: HIGH — API keys in .env.example committed to git       │
└────────────────────────────────────────────────────────────────┘

┌─ QA Agent ─────────────────────────────────────────────────────┐
│ • Test coverage: 34% (threshold: 80%)                          │
│ • No integration tests, no E2E tests                           │
└────────────────────────────────────────────────────────────────┘

┌─ Developer Agent ──────────────────────────────────────────────┐
│ • Refactoring suggestions: extract service layer, add typing   │
│ • Estimated effort: 3 days                                     │
└────────────────────────────────────────────────────────────────┘

Final report combines all findings into a structured document.
```

### When to Use Multi-Agent vs Single-Agent

| Scenario | Approach |
|----------|----------|
| "What is my IP address?" | Single agent (fast, no delegation overhead) |
| "Review this repo for security issues" | Multi-agent (parallel, specialized analysis) |
| "Fix all linting errors" | Single agent (sequential, tool-focused) |
| "Design a microservice architecture" | Multi-agent (architect + security + data) |
| "Debug this test failure" | Single agent (focused, minimal context) |

---

## 16. Task Planning Engine

Before executing any non-trivial task, the agent plans its approach. This dramatically improves output quality.

### Planning Flow

```
Analyze
  │  Understand the request, extract requirements, identify constraints
  ▼
Plan
  │  Break into steps, determine tool needs, estimate complexity
  ▼
Estimate Risk
  │  Score each step (LOW / MEDIUM / HIGH), gate on confirmation
  ▼
Execute
  │  Run steps sequentially or in parallel, collect results
  ▼
Validate
  │  Check outputs, run tests, verify against requirements
  ▼
Report
  │  Summarize what was done, what failed, what needs attention
```

### TaskPlanner Implementation

```python
@dataclass
class TaskStep:
    id: str
    description: str
    tool: str
    params: dict
    risk: str  # LOW | MEDIUM | HIGH
    depends_on: list[str] = field(default_factory=list)
    timeout: int = 30

@dataclass
class TaskPlan:
    goal: str
    steps: list[TaskStep]
    estimated_complexity: str
    requires_confirmation: bool

class TaskPlanner:
    async def create_plan(self, goal: str, context: dict) -> TaskPlan:
        """Analyze goal and generate a step-by-step plan."""
        prompt = self._build_planning_prompt(goal, context)
        plan = await self.llm.structured_output(prompt, TaskPlan)
        return self._validate_plan(plan)

    async def execute_plan(self, plan: TaskPlan, registry: ToolRegistry) -> ExecutionReport:
        """Execute plan steps respecting dependencies and risk levels."""
        results = {}
        for step in self._topological_sort(plan.steps):
            if step.risk == "HIGH":
                confirmed = await self._request_confirmation(step)
                if not confirmed:
                    results[step.id] = StepResult(skipped=True, reason="Requires confirmation")
                    continue
            result = await registry.execute(step.tool, step.params)
            results[step.id] = result
            if not result.success:
                return ExecutionReport(failed_at=step.id, error=result.error)
        return ExecutionReport(success=True, results=results)
```

### Why Planning Matters

Without planning, agents execute the first thing they think of. With planning:
- **Dependencies are resolved** — files are read before being edited
- **Risk is assessed upfront** — dangerous operations are gated
- **Parallelism is maximized** — independent steps run concurrently
- **Failures are graceful** — one failed step doesn't waste prior work
- **Output is structured** — every step produces a checkable result

---

## 17. Self-Critique & Reflection

After every significant output, the agent critiques its own work before delivering it to the user.

### Critique Loop

```
Generate Solution
      │
      ▼
Critic Agent Reviews
      │  Checks: correctness, completeness, safety, style, edge cases
      ▼
Fix Weaknesses
      │  Rewrite or patch based on critique findings
      ▼
Deliver Final Output
```

### Implementation

```python
class SelfCritique:
    def __init__(self, model_router):
        self.model = model_router

    async def critique(self, task: str, solution: str) -> CritiqueResult:
        """Review a solution and identify weaknesses."""
        prompt = f"""
        Task: {task}
        Solution: {solution}

        Review the solution for:
        1. Correctness — does it solve the task?
        2. Completeness — are there edge cases?
        3. Safety — any security or data loss risks?
        4. Style — follows best practices?
        5. Efficiency — could it be simpler?

        Return findings as a JSON array of issues.
        """
        findings = await self.model.structured_output(prompt, list[CritiqueIssue])
        return CritiqueResult(
            score=self._calculate_score(findings),
            issues=findings,
            passed=len(findings) == 0,
        )

    async def improve(self, task: str, solution: str, critique: CritiqueResult) -> str:
        """Rewrite the solution addressing all critique issues."""
        if critique.passed:
            return solution
        prompt = f"""
        Original task: {task}
        Current solution: {solution}
        Issues identified: {critique.issues}

        Rewrite the solution fixing ALL issues above.
        """
        return await self.model.generate(prompt)
```

### When to Use Self-Critique

| Scenario | Critique Level |
|----------|----------------|
| "What time is it?" | None (factual, deterministic) |
| "Write a Python function" | Light (correctness + style) |
| "Design a database schema" | Full (correctness + safety + efficiency) |
| "Execute a shell command" | None (validated by PermissionManager) |
| "Refactor this module" | Full (completeness + style + edge cases) |

---

## 18. Autonomous Workflows

VIKI can execute multi-step tasks autonomously, chaining tools and agents without user intervention between steps.

### Workflow Example

```
User: "Fix all linting issues."

1. Scan repository        →  Find all Python files
2. Run ruff check         →  Get lint error list
3. Generate fixes         →  Auto-fix trivial issues
4. Apply changes          →  Write fixed files
5. Run ruff check again   →  Verify fixes
6. Run tests              →  Ensure no regressions
7. Verify results         →  Summarize what was fixed
8. Report to user         →  "Fixed 12/15 issues. 3 manual fixes needed."
```

### Workflow Engine

```python
class Workflow:
    name: str
    steps: list[WorkflowStep]
    rollback: list[RollbackStep]

@dataclass
class WorkflowStep:
    name: str
    tool: str
    params: dict
    retry_count: int = 2
    timeout: int = 60
    on_failure: str = "stop"  # "stop" | "skip" | "retry"

class WorkflowEngine:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, workflow: Workflow, context: dict) -> WorkflowResult:
        executed = []
        for step in workflow.steps:
            result = await self._execute_with_retry(step, context)
            executed.append(step.name)
            if not result.success and step.on_failure == "stop":
                await self._rollback(workflow, executed)
                return WorkflowResult(failed_at=step.name, error=result.error)
        return WorkflowResult(success=True)
```

### Built-in Workflows

| Workflow | Steps | Risk |
|----------|-------|------|
| **lint-and-fix** | scan → run linter → generate fixes → apply → verify → test → report | MEDIUM |
| **deploy-preview** | build → test → stage → smoke-test → report | HIGH |
| **audit-dependencies** | list deps → check vulns → suggest upgrades → report | LOW |
| **backup-project** | list files → archive → compress → verify → report | MEDIUM |

---

## 19. Repository Intelligence

VIKI automatically detects the project's structure, technology stack, and conventions — then adapts its behavior.

### Auto-Detection

```python
@dataclass
class RepositoryProfile:
    languages: list[str]           # Python, TypeScript, Rust, ...
    frameworks: list[str]          # React, FastAPI, Angular, ...
    build_system: str              # pip, npm, cargo, maven, ...
    test_framework: str            # pytest, jest, vitest, ...
    has_docker: bool
    has_ci_cd: bool
    has_database: bool
    database_type: str | None      # postgresql, sqlite, mysql, ...
    cloud_provider: str | None     # aws, azure, gcp, ...
    architecture_pattern: str      # monolith, microservices, clean-arch, ...
    package_manager: str           # poetry, npm, yarn, pnpm, ...

class RepoAnalyzer:
    async def analyze(self, path: str) -> RepositoryProfile:
        """Walk the repository and detect technologies in use."""
        profile = RepositoryProfile()
        for root, _, files in os.walk(path):
            for file in files:
                await self._classify_file(file, root, profile)
        return profile

    async def _classify_file(self, file: str, root: str, profile: RepositoryProfile):
        if file == "package.json":
            profile.languages.append("JavaScript/TypeScript")
            profile.package_manager = await self._detect_pm(root)
        elif file == "pyproject.toml":
            profile.languages.append("Python")
        elif file == "Dockerfile":
            profile.has_docker = True
        # ...
```

### Behavior Adaptation

Once VIKI knows the project stack:

| Detection | Behavior Change |
|-----------|-----------------|
| **Python + FastAPI** | Suggests uvicorn, pydantic patterns, async endpoints |
| **React + TypeScript** | Uses TypeScript syntax, React hooks patterns, JSX conventions |
| **Docker present** | Runs commands inside container context, checks docker-compose |
| **pytest** | Runs `pytest -v` for tests, checks `pytest.ini` for config |
| **PostgreSQL** | Uses psycopg2 patterns, suggests connection pooling |
| **Azure deployment** | Checks for ARM/Bicep templates, suggests Azure CLI commands |

---

## 20. Tool Discovery & Auto-Registration

Instead of manually registering each tool, VIKI's `ToolRegistry` supports auto-discovery from the filesystem.

### Auto-Discovery

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._categories: dict[str, list[str]] = defaultdict(list)

    def discover(self, *paths: str | Path):
        """Scan directories for tool modules and auto-register them."""
        for path in paths:
            path = Path(path)
            if path.is_file():
                self._discover_file(path)
            elif path.is_dir():
                for file in sorted(path.rglob("*_tool.py")):
                    self._discover_file(file)

    def _discover_file(self, file: Path):
        spec = importlib.util.spec_from_file_location(file.stem, file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if (isinstance(cls, type) and issubclass(cls, BaseTool)
                    and cls is not BaseTool):
                instance = cls()
                self.register(instance)
```

### Directory Convention

```
tools/
├── filesystem_tool.py    →  auto-registers FileSystemTool
├── git_tool.py           →  auto-registers GitTool
├── database_tool.py      →  auto-registers DatabaseTool
└── docker_tool.py        →  auto-registers DockerTool
```

### Plugin System Integration

Plugins extend the tool ecosystem without modifying core code:

```python
# plugins/github_plugin/github_tool.py
class GitHubTool(BaseTool):
    name = "github"
    description = "Interact with GitHub: PRs, issues, actions, releases."
    permission_tier = PermissionTier.ELEVATED

    async def execute(self, params: dict, provider=None) -> ToolResult:
        action = params.get("action")
        # GitHub API implementation...

# Registration at startup
registry = ToolRegistry()
registry.discover("tools/", "plugins/")
```

---

## 21. Context Manager & Project Memory

Most AI assistants lose context between sessions. VIKI v2 maintains persistent project context across weeks of work.

### Context Store

```python
@dataclass
class ProjectContext:
    project_name: str
    root_path: str
    tech_stack: RepositoryProfile
    open_tasks: list[Task]
    recent_files: list[str]
    architecture_decisions: list[ADRecord]
    current_branch: str
    active_ticket: str | None

class ContextManager:
    """Maintains and retrieves project context across sessions."""

    def __init__(self, memory: ProjectMemory):
        self.memory = memory
        self._current: ProjectContext | None = None

    async def load_project(self, path: str) -> ProjectContext:
        """Load or create project context for the given path."""
        ctx = await self.memory.get_project_context(path)
        if not ctx:
            ctx = await self._bootstrap_context(path)
            await self.memory.save_project_context(ctx)
        self._current = ctx
        return ctx

    async def update_after_action(self, action: str, result: Any):
        """Update context based on what just happened."""
        if "opened file" in action:
            self._current.recent_files.append(result)
        elif "created branch" in action:
            self._current.current_branch = result
        elif "made decision" in action:
            self._current.architecture_decisions.append(result)

    def get_context_summary(self) -> str:
        """Build a compact summary for the LLM system prompt."""
        return (
            f"Project: {self._current.project_name}\n"
            f"Branch: {self._current.current_branch}\n"
            f"Stack: {', '.join(self._current.tech_stack.languages)}\n"
            f"Open: {len(self._current.open_tasks)} tasks\n"
            f"Recent: {', '.join(self._current.recent_files[-5:])}"
        )
```

### Local Knowledge Base

VIKI can index project documentation and answer questions from it:

```python
class KnowledgeBase:
    """Indexes project docs, wikis, and READMEs for semantic search."""

    def __init__(self, db_path: str, embedder: EmbeddingModel):
        self.db = sqlite3.connect(db_path)
        self.embedder = embedder

    async def index_directory(self, path: str, patterns: list[str] = None):
        """Walk directory and index matching files."""
        patterns = patterns or ["*.md", "*.rst", "*.txt", "wiki/**"]
        for pattern in patterns:
            for file in Path(path).glob(pattern):
                content = file.read_text(encoding="utf-8", errors="replace")
                await self._index_document(str(file), content)

    async def query(self, question: str, top_k: int = 5) -> list[Document]:
        """Find relevant documents for a question."""
        q_emb = await self.embedder.embed(question)
        rows = self.db.execute("""
            SELECT path, content, embedding FROM documents
        """).fetchall()
        scored = [(self._similarity(q_emb, r[2]), r[0], r[1]) for r in rows]
        scored.sort(reverse=True)
        return [Document(path=r[1], content=r[2][:2000])
                for _, r in enumerate(scored[:top_k])]
```

### Storage Options

| Option | Use Case | Pros | Cons |
|--------|----------|------|------|
| **ChromaDB** | Semantic search + metadata filtering | Fast, simple API, persistent | Adds dependency |
| **FAISS** | High-performance vector search | Blazing fast, GPU support | No built-in persistence |
| **SQLite + vectors** | Lightweight, no extra services | Zero config, always available | Slower at scale (>10K docs) |
| **Qdrant** | Production-grade vector DB | Filtering, clustering, high perf | Overkill for single-user |

---

## 22. Engineering-Specific Features

Since VIKI works with Microsoft Fabric, Power BI, SQL, and data engineering workflows, v2 includes specialized knowledge and tooling for these domains.

### Data Engineering Agent Suite

```
Data Agent
├── Fabric Agent        →  Lakehouses, Warehouses, Pipelines, Notebooks, Spark
├── Power BI Agent      →  Semantic models, DAX, reports, datasets, measures
├── SQL Agent           →  Query optimization, schema design, migrations
├── ADF Agent           →  Azure Data Factory pipelines, triggers, activities
├── Spark Agent         →  PySpark notebooks, performance tuning, debugging
└── Lakehouse Agent     →  Delta tables, partitions, Z-ordering, vacuum
```

### Fabric Agent Capabilities

| Capability | Description |
|-----------|-------------|
| **Lakehouse management** | Create, configure, optimize lakehouses |
| **Warehouse queries** | T-SQL on Fabric Warehouse, performance analysis |
| **Pipeline orchestration** | Design, debug, monitor Fabric pipelines |
| **Notebook operations** | Create, edit, run Spark notebooks |
| **Semantic model analysis** | Inspect DAX measures, optimize relationships |
| **Dataflow validation** | Check dataflow dependencies, refresh status |
| **Capacity management** | Monitor Fabric capacity, identify bottlenecks |
| **Shortcut management** | Configure OneLake shortcuts to external sources |

### Example: Fabric Workflow

```
User: "Check why the Sales dashboard refresh failed."

1.  Fabric Agent → Inspect semantic model refresh history
2.  Identify: "Sales_Measures" measure uses a DAX expression
    that references a renamed column
3.  SQL Agent → Query the warehouse to find the column
4.  Power BI Agent → Suggest fix: update measure to use new column name
5.  Apply the fix → Trigger refresh → Verify → Report
```

### Domain-Specific Tools

```python
class FabricTool(BaseTool):
    name = "fabric"
    description = "Manage Microsoft Fabric lakehouses, warehouses, pipelines, and notebooks."
    permission_tier = PermissionTier.ELEVATED
    capabilities = [
        "list_lakehouses", "run_notebook", "check_pipeline_status",
        "get_semantic_model", "optimize_delta_table",
    ]

class PowerBITool(BaseTool):
    name = "powerbi"
    description = "Analyze and manage Power BI semantic models, reports, and datasets."
    permission_tier = PermissionTier.ELEVATED
    capabilities = [
        "list_datasets", "get_measure_dax", "refresh_dataset",
        "analyze_performance", "check_dependencies",
    ]

class SQLTool(BaseTool):
    name = "sql"
    description = "Execute SQL queries, inspect schemas, optimize performance."
    permission_tier = PermissionTier.ELEVATED
    capabilities = [
        "run_query", "describe_table", "find_slow_queries",
        "suggest_indexes", "explain_plan",
    ]
```

---

## 23. Migration Plan for Existing VIKI Codebase

### Phase 1: Foundation (Week 1-2)

```
Goal: Establish the new architecture alongside the existing system.

Steps:
1. Create src/viki/v2/ directory with the new package structure
2. Implement core interfaces:
   - BaseTool, ToolRegistry, PermissionManager
   - SystemProvider abstract base
   - IntentAnalyzer, ToolSelector
3. Write providers/windows.py with initial capabilities (system info, network)
4. Write the first two tools: SystemTool, NetworkTool
5. Install new CLI entry point: `python -m viki.v2`

Validation:
- SystemTool.get_os_info() returns correct data on Windows
- NetworkTool.get_wifi_password() retrieves the current WiFi password
- IntentAnalyzer correctly routes "what is my wifi password" to NetworkTool
```

### Phase 2: Tools & Memory (Week 3-4)

```
Goal: Complete the tool registry and memory system.

Steps:
1. Implement all seven core tools:
   - SystemTool ✅
   - NetworkTool ✅
   - FileSystemTool (read/search)
   - ShellTool
   - GitTool
   - DatabaseTool
   - DevTool
2. Implement SessionMemory + ProjectMemory
3. Implement PermissionManager with confirmation flow
4. Add LinuxProvider + MacProvider

Validation:
- All tools execute correctly on at least one platform
- PermissionManager correctly blocks ADMIN actions without confirmation
- ProjectMemory persists across sessions
```

### Phase 3: Integration with Existing VIKI (Week 5-6)

```
Goal: Bridge the new tool system with the existing VIKI controller.

Strategy:
- The existing VIKIController remains the main orchestrator
- The new tool system registers as a "V2ToolBridge" skill
- Gradually replace existing skill calls with V2 tool calls
- The CognitiveRouter gains an optional V2 routing path

Steps:
1. Create V2ToolBridge skill that wraps the new tool registry
2. Modify CognitiveProcessor to include V2 tools in deliberation
3. Add VIKI_V2_MODE env var (default: off, opt-in)
4. Run A/B comparisons between v1 skills and v2 tools

Validation:
- Queries route correctly through both systems
- Latency is comparable or better
- Users can toggle between v1 and v2
```

### Phase 4: Production Hardening (Week 7-8)

```
Goal: Security audit, performance optimization, documentation.

Steps:
1. Security audit: pen-test all tools, verify sandboxing
2. Add comprehensive error handling (circuit breakers, timeouts)
3. Performance: add ToolCache for SAFE-tier results
4. Add tool usage analytics (most-used tools, failure rates)
5. Documentation: README, tool registry docs, migration guide
6. Write unit tests for every tool and provider
7. Add integration tests on Windows/Linux/macOS CI

Validation:
- All tools have >90% test coverage
- Security audit passes (no path traversal, no command injection)
- All three platforms have at least basic provider support
```

### Phase 5: Multi-Agent System (Week 9-10)

```
Goal: Deploy specialist agents alongside the core agent.

Steps:
1. Create agents/ directory with SpecialistAgent base class
2. Implement Architect, Developer, Security, QA agents
3. Implement Agent Manager for spawning/monitoring agents
4. Add multi-agent dispatch logic to CoreAgent
5. Add parallel agent execution for compound tasks (e.g., "review this repo")

Validation:
- "Review this repository" dispatches to all agents in parallel
- Each agent returns structured findings
- Final report correctly combines all findings
```

### Phase 6: Workflows & Planning (Week 11-12)

```
Goal: Add task planning, self-critique, and autonomous workflow execution.

Steps:
1. Implement TaskPlanner (Analyze → Plan → Risk → Execute → Validate → Report)
2. Implement SelfCritique loop for quality assurance
3. Implement WorkflowEngine with built-in workflows
4. Add ContextManager for cross-session project memory
5. Add Repository Intelligence (auto-detect stack, languages, frameworks)

Validation:
- "Fix all linting issues" executes as a multi-step workflow
- Self-critique catches and fixes obvious errors before delivery
- ContextManager maintains state across multiple sessions
- RepoAnalyzer correctly detects the repository stack
```

### Phase 7: Plugins & Engineering Features (Week 13-14)

```
Goal: Plugin system and domain-specific capabilities for data engineering.

Steps:
1. Implement PluginLoader with auto-discovery from plugins/ directory
2. Add Fabric, Power BI, and SQL domain-specific agents
3. Add KnowledgeBase for indexing project documentation
4. Implement tool auto-discovery (ToolRegistry.discover())
5. Add risk scoring to PermissionManager

Validation:
- Third-party plugin can be added by dropping a file in plugins/
- Fabric Agent can inspect a lakehouse and report status
- KnowledgeBase answers questions from project docs
- HIGH-risk actions require confirmation before execution
```

### Phase 8: Production Hardening (Week 15-16)

```
Goal: Security audit, performance optimization, documentation.

Steps:
1. Security audit: pen-test all tools, verify sandboxing
2. Add comprehensive error handling (circuit breakers, timeouts)
3. Performance: add ToolCache for SAFE-tier results
4. Add tool usage analytics (most-used tools, failure rates)
5. Documentation: README, tool registry docs, migration guide
6. Write unit tests for every tool, agent, and provider
7. Add integration tests on Windows/Linux/macOS CI

Validation:
- All tools have >90% test coverage
- Security audit passes (no path traversal, no command injection)
- All three platforms have at least basic provider support
```

### Phase 9: Full Migration (Week 17-18)

```
Goal: Mark old skills as deprecated, default to v2.

Steps:
1. Flip default: VIKI_V2_MODE defaults to ON
2. Add deprecation warnings to old skill system
3. Migrate all in-repo workflows to use V2 tool definitions
4. Remove old skill system (or keep as legacy bridge)

Validation:
- Full CI/CD pipeline passes with V2 default
- No feature regressions compared to v1
- Documentation fully updated
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Platform-specific API changes | All providers can be patched independently. Abstract base class defines contract |
| LLM hallucinates tool calls | ToolSelector validates against registry. Unknown tools are rejected before execution |
| Permission bypass | PermissionManager runs in a separate process (future). Audit trail is append-only |
| Performance regression | ToolCache for SAFE operations. Parallel tool execution for independent calls |
| User confusion during migration | v1 and v2 coexist. VIKI_V2_MODE env var controls which system is active |
| Multi-agent coordination failure | Agent Manager monitors all agents. Failed agents are respawned |
| Self-critique infinite loop | Maximum 2 critique iterations per output. Falls back to original after threshold |
| Autonomous workflow damage | Every workflow step is logged. Rollback steps reverse changes on failure |
| Plugin security | Plugins run in isolated subprocesses. No filesystem access without PermissionManager |

---

## Appendix: Comparison to Current Architecture

| Aspect | Current (v1) | Proposed (v2) |
|--------|-------------|---------------|
| **Intent routing** | Keyword-based classification (26 categories) | LLM-based semantic understanding |
| **Tool system** | 60+ skills with various interfaces | 7 core tools + auto-discovery + plugins |
| **Permission model** | CapabilityRegistry with 14 tiers | SAFE/ELEVATED/ADMIN + risk scoring |
| **Cross-platform** | Windows-first, Linux/macOS partial | Full SystemProvider abstraction per platform |
| **OS interaction** | Embedded in skills (shell_skill, filesystem_skill) | Abstracted via providers, tools call providers |
| **Tool discovery** | LLM tool definitions via `get_tool_definition()` | Auto-registration + directory discovery + plugins |
| **Memory** | Hierarchical (working/episodic/semantic) | Session + Project + Long-Term + Knowledge Base |
| **Agent architecture** | Single monolithic agent | Multi-agent: Architect, Developer, Security, QA, Research, Data |
| **Planning** | Immediate execution (React loop) | Analyze → Plan → Risk → Execute → Validate → Report |
| **Quality** | No self-validation | Self-critique loop: generate → review → fix → deliver |
| **Workflows** | No built-in workflows | WorkflowEngine with lint-and-fix, deploy-preview, audit-dependencies |
| **Repository context** | None | RepoAnalyzer auto-detects stack + ContextManager persists project state |
| **Domain expertise** | General-purpose prompts | Specialized Fabric, Power BI, SQL agents |
| **Execution** | ReAct loop (max 20 steps) | Same ReAct loop, standardized ToolResult format |
| **Security** | Governor, SafetyLayer, CapabilityRegistry | Governor + PermissionManager + AuditTrail + Sandbox |
| **WiFi password** | Not possible (routes to web search) | SystemProvider → Windows/Linux/Mac → returns directly |
