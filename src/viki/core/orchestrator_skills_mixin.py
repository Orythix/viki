"""Skill registration, execution, validation, and MCP attachment.

Extracted from the VIKIController god-module; mixed into
viki.core.orchestrator.VIKIController.
"""

import asyncio
import importlib
import os
import time
from typing import Any

from viki.config.logger import viki_logger
from viki.core.orchestrator_helpers import json_type_matches
from viki.core.security_guard import safe_for_log


class ControllerSkillsMixin:
    def _apply_skill_aliases(self) -> None:
        alias_pairs = [
            ("look", "look_at_screen"),
            ("highlight", "draw_overlay"),
            ("focus", "mount_focus"),
            ("net_scan", "security_tools"),
            ("web_audit", "security_tools"),
            ("sniffer", "security_tools"),
            ("evolve", "internal_forge"),
            ("recall", "recall"),
            ("python", "python_interpreter"),
            ("search", "research"),
            ("read", "research"),
            ("say", "voice"),
            ("speak", "voice"),
            ("pause", "media_control"),
            ("play", "media_control"),
            ("media", "media_control"),
            ("volume", "media_control"),
            ("copy", "clipboard"),
            ("paste", "clipboard"),
            ("windows", "window_manager"),
            ("minimize", "window_manager"),
            ("maximize", "window_manager"),
            ("powershell", "shell"),
            ("messaging", "messaging"),
            ("clawdis", "messaging"),
            ("notify", "notification"),
            ("toast", "notification"),
            ("video", "short_video_agent"),
            ("short", "short_video_agent"),
            ("antivirus", "endpoint_guard"),
            ("cache", "cache_pilot"),
            ("weaver", "context_weaver"),
            ("trace", "mind_trace"),
            ("audit", "autonomous_auditor"),
            ("logs", "log_voyager"),
            ("mutation", "mutation_pilot"),
            ("market", "market_explorer"),
            ("mem", "memory"),
            ("sovereign", "memory"),
        ]
        for alias_name, target_name in alias_pairs:
            target = self.skill_registry.get_skill(target_name)
            if target is not None:
                self.skill_registry.skills[alias_name] = target

    def check_skill_health(self) -> None:
        """Optional startup check: log warnings for degraded runtime or misconfigured integrations."""
        self.health_reporter.check_skill_health()

    def _should_checkpoint(self, skill_name: str) -> bool:
        """True if this skill modifies files or runs shell and we should create a checkpoint before executing."""
        if skill_name in ("dev_tools", "shell", "filesystem_skill"):
            return True
        return False

    def _diff_preview(self, skill_name: str, params: dict[str, Any]) -> str:
        """Short preview of the action for confirmation message (Gemini CLI-style)."""
        if skill_name == "dev_tools":
            path = params.get("path", "?")
            if params.get("content") is not None:
                content = params.get("content", "")
                n = len(content)
                first_line = content.split("\n")[0][:60] if content else ""
                return f"Target: {path} | new content: {n} chars" + (
                    f" | first line: {first_line}..." if first_line else ""
                )
            if params.get("target") is not None and params.get("replacement") is not None:
                t, r = params.get("target", ""), params.get("replacement", "")
                return f"Target: {path} | patch: replace {len(t)} chars with {len(r)} chars"
        if skill_name == "shell":
            cmd = safe_for_log(params.get("command", "?"), max_len=120)
            return f"Command: {cmd}"
        if skill_name == "filesystem_skill":
            path = safe_for_log(params.get("path", "?"))
            return f"Target: {path}"
        return ""

    async def _execute_skill(
        self, skill_name: str, params: dict[str, Any], budget: dict[str, Any]
    ) -> tuple:
        """
        Execute a skill with timeout and optional checkpoint. Single place for execution logic.
        Returns (result_str_or_None, error_str_or_None, latency_float).
        """
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return None, f"Skill '{skill_name}' not found.", 0.0

        # Circuit breaker check
        if hasattr(self.skill_registry, "is_skill_available"):
            if not self.skill_registry.is_skill_available(skill_name):
                return None, f"Skill '{skill_name}' is temporarily unavailable (circuit open).", 0.0

        if self._should_checkpoint(skill_name):
            self.history.create_checkpoint(self, skill_name, params)
        budget_time = budget.get("time") or self.SKILL_TIMEOUT_BUDGET_DEFAULT
        skill_timeout = min(
            self.SKILL_TIMEOUT_MAX,
            max(self.SKILL_TIMEOUT_MIN, budget_time * self.SKILL_TIMEOUT_BUDGET_MULTIPLIER),
        )
        start_exec = time.time()
        try:
            result = await asyncio.wait_for(skill.execute(params), timeout=skill_timeout)
            latency = time.time() - start_exec
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, latency, True, None)
            except Exception:
                pass
            return (str(result), None, latency)
        except TimeoutError:
            err_msg = f"Action timed out (limit {skill_timeout}s)."
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                pass
            return None, err_msg, 0.0
        except Exception as e:
            err_msg = f"Action failed: {e}"
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                pass
            return None, err_msg, 0.0

    def _get_planner_callbacks(
        self, session_id: str, budget: dict[str, Any], on_event: Any | None
    ) -> dict[str, Any]:
        """Maps TaskGraph node types to functional skill executions for the FSM pipeline."""

        async def _generic_exec(task: Any, skill: str, forced_params: dict[str, Any] | None = None):
            if on_event:
                on_event("status", f"PLANNER: {task.description}")
            params = (task.parameters if isinstance(task.parameters, dict) else {}).copy()
            if forced_params:
                params.update(forced_params)

            # Special case for shell commands: ensure 'command' is present
            if skill == "shell" and "command" not in params:
                # If the planner put the command in 'parameters' but not under 'command' key
                # though typically parameters IS the dict.
                pass

            res, err, lat = await self._execute_skill(skill, params, budget)
            if err:
                raise RuntimeError(err)
            return res

        async def _analyze(task: Any):
            if on_event:
                on_event("status", f"PLANNER ANALYZING: {task.description}")
            model = self.model_router.get_model(["reasoning", "fast_response"])
            prompt = (
                f"You are the VIKI Execution Agent.\n"
                f"Goal: {self.world.state.active_goal}\n"
                f"Current Task: {task.description}\n"
                f"Context: {task.parameters}\n\n"
                f"Provide a technical analysis or plan for this specific step."
            )
            return await model.chat([{"role": "user", "content": prompt}])

        return {
            "search_repo": lambda t: _generic_exec(t, "code_search"),
            "read_file": lambda t: _generic_exec(t, "dev_tools", {"action": "read_file"}),
            "write": lambda t: _generic_exec(t, "dev_tools", {"action": "write_file"}),
            "patch": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "run_tests": lambda t: _generic_exec(t, "shell"),
            "refactor": lambda t: _generic_exec(t, "dev_tools", {"action": "patch_file"}),
            "analyze": _analyze,
            "reflect": _analyze,
            "shell": lambda t: _generic_exec(t, "shell"),
            "create": lambda t: _generic_exec(t, "shell"),
        }

    def _json_type_matches(self, value: Any, expected_type: str) -> bool:
        return json_type_matches(value, expected_type)

    def _validate_required_params(self, required: list[str], params: dict[str, Any]) -> str | None:
        return self.tool_contract.validate_required_params(required, params)

    def _validate_param_spec(self, field: str, spec: dict[str, Any], val: Any) -> str | None:
        return self.tool_contract.validate_param_spec(field, spec, val)

    def _validate_property_constraints(
        self, props: dict[str, Any], params: dict[str, Any]
    ) -> str | None:
        return self.tool_contract.validate_property_constraints(props, params)

    def _validate_tool_contract_params(self, skill_name: str, params: dict[str, Any]) -> str | None:
        return self.tool_contract.validate_params(skill_name, params)

    def _validate_skill_output(self, skill_name: str, output: Any) -> str | None:
        return self.tool_contract.validate_output(skill_name, output)

    def _register_default_skills(self):
        from viki.skills.lazy_skill import LazySkillProxy

        allowlist = self.soul.config.get("skill_allowlist")
        low_resource = bool(
            (self.settings.get("system") or {}).get("low_resource_mode")
            or os.environ.get("VIKI_LOW_RESOURCE", "").lower() in ("1", "true", "yes")
        )

        def _load_skill(module_path: str, class_name: str, *args):
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, class_name, None)
                if not cls:
                    # Case-insensitive fallback
                    for attr in dir(module):
                        if attr.lower() == class_name.lower():
                            cls = getattr(module, attr)
                            break
                if not cls:
                    return None

                # Check constructor signature or just try-catch
                try:
                    return cls(*args)
                except TypeError:
                    # Fallback for skills that don't accept controller yet
                    return cls()
            except Exception as e:
                viki_logger.warning(f"Skill '{class_name}' from {module_path} disabled: {e}")
                self.disabled_skills[class_name] = str(e)
                return None

        # Eager skills: cheap to import and used on the hot path.
        eager_specs = [
            ("viki.skills.builtins.time_skill", "TimeSkill", ()),
            ("viki.skills.builtins.math_skill", "MathSkill", ()),
            ("viki.skills.builtins.filesystem_skill", "FileSystemSkill", (self,)),
            ("viki.skills.thinking", "ThinkingSkill", ()),
            ("viki.skills.builtins.system_control_skill", "SystemControlSkill", ()),
            ("viki.skills.builtins.research_skill", "ResearchSkill", (self,)),
            ("viki.skills.builtins.dev_skill", "DevSkill", (self,)),
            ("viki.skills.builtins.voice_skill", "VoiceSkill", (self.voice_module, self)),
            ("viki.skills.builtins.sfs_skill", "SemanticFSSkill", (self,)),
            ("viki.skills.builtins.security_skill", "SecuritySkill", ()),
            ("viki.skills.builtins.endpoint_guard_skill", "EndpointGuardSkill", (self,)),
            ("viki.skills.creation.forge", "ModelForgeSkill", (self,)),
            ("viki.skills.builtins.recall_skill", "RecallSkill", (self,)),
            ("viki.skills.builtins.memory_skill", "MemorySkill", (self,)),
            ("viki.skills.builtins.media_skill", "MediaControlSkill", ()),
            ("viki.skills.builtins.clipboard_skill", "ClipboardSkill", ()),
            ("viki.skills.builtins.window_management_skill", "WindowManagerSkill", ()),
            ("viki.skills.builtins.shell_skill", "ShellSkill", (self,)),
            ("viki.skills.builtins.notification_skill", "NotificationSkill", ()),
            ("viki.skills.builtins.coding_workflow_skill", "CodingWorkflowSkill", (self,)),
            ("viki.skills.builtins.lsp_skill", "LspSkill", (self,)),
        ]
        # v27: Dynamic Skill Discovery for Builtins
        import pkgutil

        import viki.skills.builtins as builtins_pkg

        discovered_specs = []
        registered_modules = {s[0] for s in eager_specs} | {s[2] for s in self._LAZY_SKILL_SPECS}

        for _, modname, ispkg in pkgutil.iter_modules(builtins_pkg.__path__):
            if ispkg:
                continue
            full_modname = f"viki.skills.builtins.{modname}"
            if full_modname in registered_modules:
                continue

            # Skip known helpers or non-skill modules
            if modname in ("code_index_watcher", "legacy_math"):
                continue

            # Simple heuristic: CamelCase class name from snake_case module
            class_name = "".join(word.capitalize() for word in modname.split("_"))
            if not class_name.endswith("Skill") and class_name not in ("LSPSkill", "SFS"):
                # Avoid double "Skill" but ensure it's there for most
                class_name += "Skill"

            discovered_specs.append((full_modname, class_name, (self,)))
            viki_logger.debug(f"Discovered skill: {class_name} in {full_modname}")

        all_skills = []
        for module_path, class_name, args in eager_specs + discovered_specs:
            skill = _load_skill(module_path, class_name, *args)
            if skill is not None:
                all_skills.append(skill)

        # Lazy heavy skills: register a proxy so they appear in the registry
        # but only import when first invoked.
        for spec in self._LAZY_SKILL_SPECS:
            sname, sdesc, smod, scls, needs_ctrl, stier = spec

            def _ctor(ctrl, scls=scls, needs_ctrl=needs_ctrl):
                if scls == "SwarmSkill":
                    return (ctrl.swarm, ctrl)
                return (ctrl,) if needs_ctrl else ()

            try:
                proxy = LazySkillProxy(
                    name=sname,
                    description=sdesc,
                    module_path=smod,
                    class_name=scls,
                    ctor_args=_ctor,
                    controller=self,
                    safety_tier=stier,
                )
                all_skills.append(proxy)
            except Exception as e:
                viki_logger.warning(f"LazySkillProxy '{sname}' failed: {e}")
                self.disabled_skills[scls] = str(e)

        # Low-resource mode: also lazify dev/research/voice etc. is overkill;
        # we only drop strictly optional eager skills that would never get
        # used unless the user asks. Currently the eager set is already lean,
        # so the flag mainly affects proactive loops downstream. Surface a
        # log line so operators know the mode is active.
        if low_resource:
            viki_logger.info(
                "VIKIController: low_resource_mode is ON — proactive loops "
                "(wellness, dream, continuous-learning, startup pulse) will be skipped."
            )
            self.low_resource_mode = True
        else:
            self.low_resource_mode = False

        allowed = set(allowlist) if allowlist else None
        for skill in all_skills:
            if allowed is None or skill.name in allowed:
                self.skill_registry.register_skill(skill)

        # v26: Load Sovereign Tool Hub (100+ Skills)
        library_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "sovereign_library.json",
        )
        self.skill_registry.load_sovereign_library(library_path, self)

        # Aliases: only add if target skill is registered
        self._apply_skill_aliases()

    def _skill_action_severity(self, skill_name: str, params: dict[str, Any]) -> str:
        skill_obj = self.skill_registry.get_skill(skill_name) if self.skill_registry else None
        if skill_obj is not None:
            st = (getattr(skill_obj, "safety_tier", None) or "safe").lower()
            if st == "destructive":
                return "destructive"
            if st == "medium":
                return "medium"
            if getattr(skill_obj, "requires_user_confirmation", False):
                return "medium"
        return self.safety.get_action_severity(skill_name, params)

    def attach_mcp_skills_sync(self, config_path: str | None = None) -> int:
        """
        P0 fix: actually wire MCP skills into the controller at boot time.

        Loads `viki/config/mcp_servers.yaml`, connects to each server, and
        registers every advertised tool as a `MCPSkillProxy` on the skill
        registry. Tolerates missing SDK / empty config / connection errors
        so VIKI keeps booting without MCP. Returns the count of skills
        installed (0 if disabled).
        """
        try:
            from viki.integrations.mcp_client import attach_mcp_skills
        except Exception as e:
            viki_logger.debug("MCP wiring skipped: import failed: %s", e)
            return 0
        try:
            try:
                asyncio.get_running_loop()
                # If a loop is already running we cannot block on it; spawn a
                # background task and return immediately. Tools will register
                # asynchronously.
                asyncio.ensure_future(self._attach_mcp_async(config_path))
                return 0
            except RuntimeError:
                installed = asyncio.run(attach_mcp_skills(self, config_path))
        except Exception as e:
            viki_logger.warning("MCP wiring failed: %s", e)
            return 0
        self.mcp_skill_count = int(installed or 0)
        if self.mcp_skill_count:
            viki_logger.info("MCP: %d external tools registered as skills.", self.mcp_skill_count)
        return self.mcp_skill_count

    async def _attach_mcp_async(self, config_path: str | None = None) -> int:
        try:
            from viki.integrations.mcp_client import attach_mcp_skills

            installed = await attach_mcp_skills(self, config_path)
        except Exception as e:
            viki_logger.debug("MCP async attach failed: %s", e)
            return 0
        self.mcp_skill_count = int(installed or 0)
        if self.mcp_skill_count:
            viki_logger.info("MCP: %d external tools registered as skills.", self.mcp_skill_count)
        return self.mcp_skill_count
