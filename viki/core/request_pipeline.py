"""
Request processing pipeline (preflight stages).

Extracted from VIKIController so orchestration stays testable and incremental
stages can be added per ARCHITECTURE_REFACTOR.md without growing _process_request_impl.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol

from viki.config.logger import viki_logger


@dataclass
class RequestContext:
    """Mutable context carried through preflight and into deliberation."""

    user_input: str
    session_id: str
    on_event: Any = None
    attachment_paths: Optional[List[str]] = None
    narrative_wisdom: Any = None
    wisdom_block: str = ""
    safe_input: str = ""


class PreflightStage(Protocol):
    """Single async step; return a user-facing string to short-circuit, or None to continue."""

    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]: ...


class _SuperAdminStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        if getattr(ctrl.super_admin, "shutdown_triggered", False):
            return "HALTED"
        try:
            if ctrl.super_admin and ctrl.super_admin.check_command(ctx.user_input):
                return "HALTED"
        except Exception as e:
            viki_logger.debug(f"Super admin kill switch check failed: {e}")
        return None


class _AttachmentStage:
    """
    P1: pipe attachments through perception. Images run through the
    `vision`/`look_at_screen` skill, audio runs through `whisper_skill`.
    Text-like attachments are inlined verbatim. Captions / transcripts are
    stitched into the user input so the deliberation layer sees them.
    """

    IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
    AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"}
    TEXT_EXT = {".txt", ".md", ".rst", ".log", ".csv", ".json", ".yaml", ".yml"}

    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        if not ctx.attachment_paths:
            return None
        registry = getattr(ctrl, "skill_registry", None)
        captions: List[str] = []
        for path in ctx.attachment_paths:
            try:
                ext = self._extension(path)
                if ext in self.IMAGE_EXT and registry is not None:
                    captions.append(await self._caption_image(registry, path))
                elif ext in self.AUDIO_EXT and registry is not None:
                    captions.append(await self._transcribe_audio(registry, path))
                elif ext in self.TEXT_EXT:
                    captions.append(self._inline_text(path))
                else:
                    captions.append(f"[Attachment {path} (unrecognized type)]")
            except Exception as e:
                viki_logger.debug("attachment %s failed: %s", path, e)
                captions.append(f"[Attachment {path}: error {e}]")
        if captions:
            ctx.user_input = "\n\n".join(captions) + "\n\n" + ctx.user_input
        return None

    @staticmethod
    def _extension(path: str) -> str:
        import os
        return os.path.splitext(path)[1].lower()

    async def _caption_image(self, registry: Any, path: str) -> str:
        skill = (
            registry.get_skill("vision")
            or registry.get_skill("look_at_screen")
            or registry.get_skill("describe_image")
        )
        if skill is None:
            return f"[Image {path} (no vision skill available)]"
        try:
            result = await skill.execute({"image_path": path, "path": path})
        except TypeError:
            result = await skill.execute({"image_path": path})
        return f"[Image attachment: {path}]\n{str(result).strip()[:1500]}"

    async def _transcribe_audio(self, registry: Any, path: str) -> str:
        skill = registry.get_skill("whisper") or registry.get_skill("audio_transcribe")
        if skill is None:
            return f"[Audio {path} (no whisper skill available)]"
        try:
            result = await skill.execute({"audio_path": path, "path": path})
        except TypeError:
            result = await skill.execute({"audio_path": path})
        return f"[Audio attachment: {path}]\nTranscript:\n{str(result).strip()[:2000]}"

    @staticmethod
    def _inline_text(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(8000)
        except Exception as e:
            return f"[Text attachment {path}: {e}]"
        return f"[Text attachment: {path}]\n{content}"


class _GovernorStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        if ctrl.governor.check_shutdown(ctx.user_input):
            return "Orythix — Quiescent (shutdown key 970317 accepted)"

        if ctrl.governor.is_quiescent:
            if ctrl.governor.check_reawaken(ctx.user_input):
                return "Orythix — Reawakened. Systems Online."
            return "Status: Quiescent. Systems Frozen."

        narrative_wisdom = ctrl.memory.episodic.get_semantic_knowledge(limit=3)
        ctx.narrative_wisdom = narrative_wisdom
        wisdom_list = narrative_wisdom if isinstance(narrative_wisdom, list) else []
        ctx.wisdom_block = "\n".join(
            [
                f"- [{(w.get('category') or 'general').upper()}]: {w.get('insight', '')}"
                for w in wisdom_list
            ]
        )

        allowed, reason = await ctrl.governor.veto_check(
            ctx.user_input, model_router=ctrl.model_router, wisdom=ctx.wisdom_block
        )
        if not allowed:
            viki_logger.warning(f"Governor Vetoed Request: {reason}")
            return f"I cannot comply. {reason}"
        return None


class _SafetyStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        ctx.safe_input = ctrl.safety.validate_request(ctx.user_input)

        security_scan_requests = ctrl.settings.get("system", {}).get("security_scan_requests")
        if security_scan_requests is None:
            security_scan_requests = bool(getattr(ctrl.safety, "security_prompt", None))
        if security_scan_requests:
            llm = ctrl.model_router.get_model()
            scan_result = await ctrl.safety.scan_request(llm, ctx.user_input)
            if not scan_result.get("safe", True):
                viki_logger.warning(f"Security scan refused request: {scan_result.get('reason', '')}")
                return f"I cannot comply. {scan_result.get('reason', 'Request blocked by security policy.')}"
        return None


class _SignalsResetStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        ctrl.interrupt_signal.clear()
        ctrl.signals.decay_signals()
        return None


class _PendingOpsStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        pending_ops = ctrl.pending_ops_plans.get(ctx.session_id)
        if not pending_ops:
            return None
        raw_lower = ctx.user_input.strip().lower()
        affirmatives = ("yes", "y", "confirm", "ok", "proceed", ctrl.CONFIRM_TOKEN)
        negatives = ("no", "n", "reject", "cancel", ctrl.REJECT_TOKEN)
        if raw_lower in affirmatives:
            ctrl.pending_ops_plans.pop(ctx.session_id, None)
            return await ctrl._apply_ops_plan(pending_ops, session_id=ctx.session_id)
        if raw_lower in negatives:
            ctrl.pending_ops_plans.pop(ctx.session_id, None)
            return "OpsPlan cancelled."
        return "OpsPlan pending approval. Confirm with yes/confirm or cancel with no/reject."


class _PendingActionStage:
    async def run(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        pending_action = ctrl.pending_actions.get(ctx.session_id)
        if not pending_action:
            return None
        raw_lower = ctx.user_input.strip().lower()
        affirmatives = ("yes", "y", "confirm", "ok", "proceed", ctrl.CONFIRM_TOKEN)
        negatives = ("no", "n", "reject", "cancel", ctrl.REJECT_TOKEN)
        if raw_lower in affirmatives:
            ctrl.pending_actions.pop(ctx.session_id, None)
            skill_name = pending_action.skill_name
            params = (pending_action.parameters or {}).copy()
            check_res = ctrl.capabilities.check_permission(skill_name, params=params)
            if not check_res.allowed:
                return f"Confirmation rejected: capability check failed — {check_res.reason}"
            if not ctrl.safety.validate_action(skill_name, params):
                viki_logger.warning(f"Safety: validate_action blocked {skill_name}")
                return "Action blocked by safety policy."
            if ctrl.world.state.safety_zones.get(params.get("path", "")) == "protected":
                return "Safety Block: Target is in a protected zone."
            if ctrl.shadow_mode:
                return f"[Shadow Mode] Would have executed: {skill_name}({params}). Set shadow_mode: false to run for real."
            if ctx.on_event:
                ctx.on_event("status", f"EXECUTING {skill_name}")
            budget = ctrl.budgets.get("general", ctrl.budgets["general"])
            result, err, latency = await ctrl._execute_skill(skill_name, params, budget)
            if err:
                ctrl.skill_registry.record_execution(skill_name, False, 0.0)
                return err
            ctrl.skill_registry.record_execution(skill_name, True, latency)
            return f"Done. {result[:500]}"
        if raw_lower in negatives:
            ctrl.pending_actions.pop(ctx.session_id, None)
            return "Action cancelled."
        return "Please confirm with yes/confirm or cancel with no/reject."


class RequestPipeline:
    """Runs ordered preflight stages until one returns a terminal response."""

    def __init__(self, stages: Optional[List[PreflightStage]] = None):
        if stages is None:
            stages = [
                _SuperAdminStage(),
                _AttachmentStage(),
                _GovernorStage(),
                _SafetyStage(),
                _SignalsResetStage(),
                _PendingOpsStage(),
                _PendingActionStage(),
            ]
        self._stages: List[PreflightStage] = stages

    async def run_preflight(self, ctrl: Any, ctx: RequestContext) -> Optional[str]:
        for stage in self._stages:
            out = await stage.run(ctrl, ctx)
            if out is not None:
                return out
        return None


def build_default_preflight_pipeline() -> RequestPipeline:
    return RequestPipeline()
