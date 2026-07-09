import asyncio
import importlib
import os
import pkgutil
import time
from typing import Any

from viki.config.logger import viki_logger
from viki.core.orchestrator_helpers import _LAZY_SKILL_SPECS


class SkillsMixin:
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
                    for attr in dir(module):
                        if attr.lower() == class_name.lower():
                            cls = getattr(module, attr)
                            break
                if not cls:
                    return None
                try:
                    return cls(*args)
                except TypeError:
                    return cls()
            except Exception as e:
                viki_logger.warning(f"Skill '{class_name}' from {module_path} disabled: {e}")
                self.disabled_skills[class_name] = str(e)
                return None

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

        import viki.skills.builtins as builtins_pkg

        discovered_specs = []
        registered_modules = {s[0] for s in eager_specs} | {s[2] for s in _LAZY_SKILL_SPECS}

        for _, modname, ispkg in pkgutil.iter_modules(builtins_pkg.__path__):
            if ispkg:
                continue
            full_modname = f"viki.skills.builtins.{modname}"
            if full_modname in registered_modules:
                continue
            if modname in ("code_index_watcher", "computer_use"):
                continue
            class_name = "".join(word.capitalize() for word in modname.split("_"))
            if not class_name.endswith("Skill") and class_name not in ("LSPSkill", "SFS"):
                class_name += "Skill"
            discovered_specs.append((full_modname, class_name, (self,)))
            viki_logger.debug(f"Discovered skill: {class_name} in {full_modname}")

        all_skills = []
        for module_path, class_name, args in eager_specs + discovered_specs:
            skill = _load_skill(module_path, class_name, *args)
            if skill is not None:
                all_skills.append(skill)

        for spec in _LAZY_SKILL_SPECS:
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
                self.disabled_skills[sname] = str(e)

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

        library_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "sovereign_library.json",
        )
        self.skill_registry.load_sovereign_library(library_path, self)

        self._apply_skill_aliases()

    def attach_mcp_skills_sync(self, config_path: str | None = None) -> int:
        try:
            from viki.integrations.mcp_client import attach_mcp_skills
        except Exception as e:
            viki_logger.debug("MCP wiring skipped: import failed: %s", e)
            return 0
        try:
            try:
                asyncio.get_running_loop()
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

    def _get_skills_context(self) -> str:
        return self.skill_registry.get_context_description()

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

    async def _execute_skill(
        self, skill_name: str, params: dict[str, Any], budget: dict[str, Any]
    ) -> tuple:
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            return None, f"Skill '{skill_name}' not found.", 0.0

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
                viki_logger.warning("failed to emit skill execution telemetry")
            return (str(result), None, latency)
        except TimeoutError:
            err_msg = f"Action timed out (limit {skill_timeout}s)."
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                viki_logger.warning("failed to emit skill execution telemetry")
            return None, err_msg, 0.0
        except Exception as e:
            err_msg = f"Action failed: {e}"
            try:
                from viki.core.usage_log import emit_skill_execution

                emit_skill_execution(skill_name, time.time() - start_exec, False, err_msg)
            except Exception:
                viki_logger.warning("failed to emit skill execution telemetry")
            return None, err_msg, 0.0

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
