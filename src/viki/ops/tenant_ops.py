from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class OpsFact:
    """A single grounded fact used to plan an operation."""

    key: str
    value: str


@dataclass
class MessageDraft:
    """A draft to be sent via one or more outbound channels."""

    channel: str  # e.g. "email", "whatsapp", "discord", "telegram"
    text: str
    recipient: str | None = None  # Optional routing info for connectors


@dataclass
class ApprovalRequirement:
    """Describes what must be approved before execution."""

    required: bool = True
    reasons: list[str] = field(default_factory=list)
    what_to_approve: list[str] = field(
        default_factory=list
    )  # e.g. ["send_messages", "apply_event_change"]


@dataclass
class OpsPlan:
    """
    Structured "update plan" created before executing any external side effects.
    This makes ops auditable and enables human-in-the-loop approvals.
    """

    tenant_id: str
    update_type: str  # e.g. "schedule_change", "cancellation", "reminder"
    facts_used: list[OpsFact] = field(default_factory=list)

    # Proposed event/system changes (tenant-specific connector schema).
    proposed_changes: dict[str, Any] = field(default_factory=dict)

    # Draft communications per channel.
    message_drafts: list[MessageDraft] = field(default_factory=list)

    # Approval gate.
    approval: ApprovalRequirement = field(default_factory=ApprovalRequirement)

    # Additional constraints or refusal notes.
    safety_constraints: list[str] = field(default_factory=list)


class TenantConnector(Protocol):
    """
    Connector interface that normalizes tenant ops in/out.
    Concrete implementations are tenant-specific.
    """

    tenant_id: str

    async def fetch_state(self, event_id: str | None = None) -> dict[str, Any]:
        """Fetch tenant state required to plan an operation."""

    async def apply_changes(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply approved changes to the tenant systems."""

    async def send_messages(self, drafts: list[MessageDraft]) -> dict[str, Any]:
        """Send approved messages via tenant outbound channels."""


class OpsPlanner(Protocol):
    """Planner interface: turns a request into a structured OpsPlan."""

    async def plan(self, tenant_id: str, request: str) -> OpsPlan: ...


class NoopOpsPlanner:
    """
    Minimal starter planner that creates an approval-only plan.
    This is intentionally safe and side-effect free.
    """

    async def plan(self, tenant_id: str, request: str) -> OpsPlan:
        # Keep the method async-friendly without introducing side effects.
        await asyncio.sleep(0)
        plan = OpsPlan(
            tenant_id=tenant_id,
            update_type="unknown",
            facts_used=[],
            proposed_changes={},
            message_drafts=[
                MessageDraft(
                    channel="internal",
                    text=f"(Plan placeholder) Need tenant policy + connector state to plan request: {request}",
                )
            ],
            approval=ApprovalRequirement(
                required=True,
                reasons=["Side-effectful operations require a grounded plan and human approval."],
                what_to_approve=["apply_event_change", "send_messages"],
            ),
            safety_constraints=["No execution performed by NoopOpsPlanner."],
        )
        return plan


class SimpleOpsPlanner(OpsPlanner):
    """
    Minimal first ops planner:
    - Parses event/club scheduling intents
    - Produces an OpsPlan with message drafts + an approval gate
    """

    def __init__(self, controller: Any = None):
        self.controller = controller

    FOR_CLAUSE_TOKEN = " for "

    async def plan(self, tenant_id: str, request: str) -> OpsPlan:  # NOSONAR
        await asyncio.sleep(0)
        text = (request or "").strip()
        req_lower = text.lower()

        update_type = "schedule_change"
        title = "Club Event"
        time_str = "tomorrow at 2pm"

        # Cancellation intent
        if any(k in req_lower for k in ("cancel", "cancellation", "remove", "delete")):
            update_type = "cancellation"

        import re as _re

        # Prefer extracting title before the time window:
        # "Schedule a <title> tomorrow at 2pm"
        mt_title = _re.search(
            r"(schedule|appointment)\s+(?:a\s+)?(?P<title>.+?)\s+(tomorrow|today)\s+at",
            text,
            flags=_re.IGNORECASE,
        )
        if mt_title and mt_title.group("title"):
            title = mt_title.group("title").strip()[:60] or title
        else:
            # Fallback: try "for <X>" clause.
            title_guess = None
            if self.FOR_CLAUSE_TOKEN in f" {req_lower} ":
                idx = req_lower.find(self.FOR_CLAUSE_TOKEN)
                if idx != -1:
                    title_guess = text[idx + len(self.FOR_CLAUSE_TOKEN) :].strip()
            if title_guess:
                for cut in (" tomorrow", " today", " tonight", " at ", " on "):
                    if cut in title_guess.lower():
                        title_guess = title_guess[: title_guess.lower().find(cut)].strip()
                        break
                if title_guess:
                    title = title_guess[:60] or title

        # Time heuristic
        mt = _re.search(r"(tomorrow|today)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", req_lower)
        if mt:
            day = mt.group(1)
            h = mt.group(2)
            minutes = mt.group(3)
            ampm = mt.group(4) or ""
            time_str = (
                f"{day} at {h}" + (f":{minutes}" if minutes else "") + (f"{ampm}" if ampm else "")
            )
        else:
            mt2 = _re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", req_lower)
            if mt2:
                h = mt2.group(1)
                minutes = mt2.group(2)
                ampm = mt2.group(3)
                time_str = f"{h}" + (f":{minutes}" if minutes else "") + f"{ampm}"

        recipient = "club_team"
        if "team" in req_lower:
            recipient = "team"

        facts_used: list[OpsFact] = []
        if self.controller is not None and getattr(self.controller, "learning", None) is not None:
            try:
                lessons = self.controller.learning.get_relevant_lessons(text, limit=3)
                for l in lessons:
                    facts_used.append(OpsFact(key="lesson", value=str(l)[:220]))
            except Exception:
                pass

        proposed_changes = {
            "update_type": update_type,
            "title": title,
            "time": time_str,
            "recipient": recipient,
        }

        message_drafts = [
            MessageDraft(
                channel="telegram",
                recipient=recipient,
                text=f"Ops update: {title} ({update_type.replace('_', ' ')}) at {time_str}.",
            ),
            MessageDraft(
                channel="discord",
                recipient=recipient,
                text=f"Ops update: {title} ({update_type.replace('_', ' ')}) at {time_str}.",
            ),
        ]

        approval = ApprovalRequirement(
            required=True,
            reasons=["Event/club scheduling and messaging have side effects."],
            what_to_approve=["apply_event_change", "send_messages"],
        )

        return OpsPlan(
            tenant_id=tenant_id,
            update_type=update_type,
            facts_used=facts_used,
            proposed_changes=proposed_changes,
            message_drafts=message_drafts,
            approval=approval,
            safety_constraints=["No execution before approval."],
        )


class ControllerTenantConnector:
    """
    Connector that executes via VIKI skills (calendar + messaging),
    using the controller's internal tool contract validation.
    """

    def __init__(self, controller: Any, tenant_id: str = "default"):
        self.controller = controller
        self.tenant_id = tenant_id
        self._budget = controller.budgets.get("general", {"time": 5})

    async def fetch_state(self, event_id: str | None = None) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"event_id": event_id}

    async def _run_skill_checked(self, skill_name: str, params: dict[str, Any]) -> dict[str, Any]:
        contract_err = self.controller._validate_tool_contract_params(skill_name, params)
        if contract_err:
            return {"ok": False, "error": contract_err}

        result, err, latency = await self.controller._execute_skill(
            skill_name, params, self._budget
        )
        if err:
            return {"ok": False, "error": err}

        output_err = self.controller._validate_skill_output(skill_name, result)
        if output_err:
            return {"ok": False, "error": output_err}

        return {"ok": True, "result": result, "latency": latency}

    async def apply_changes(self, changes: dict[str, Any]) -> dict[str, Any]:
        update_type = changes.get("update_type")
        title = changes.get("title")

        calendar = self.controller.skill_registry.get_skill("calendar")
        if calendar is None:
            return {"ok": False, "error": "calendar skill not available"}

        if update_type == "schedule_change":
            return {
                "ok": True,
                "calendar": await self._run_skill_checked(
                    "calendar", {"action": "add", "title": title, "time": changes.get("time")}
                ),
            }

        if update_type == "cancellation":
            return {
                "ok": True,
                "calendar": await self._run_skill_checked(
                    "calendar", {"action": "remove", "title": title}
                ),
            }

        return {"ok": False, "error": f"Unknown update_type: {update_type}"}

    async def send_messages(self, drafts: list[MessageDraft]) -> dict[str, Any]:
        messaging = self.controller.skill_registry.get_skill("messaging")
        if messaging is None:
            return {"ok": False, "error": "messaging skill not available"}

        results = []
        for d in drafts:
            if d.channel not in ("telegram", "discord", "slack", "whatsapp"):
                results.append({"channel": d.channel, "ok": False, "error": "unsupported channel"})
                continue
            results.append(
                {
                    "channel": d.channel,
                    **(
                        await self._run_skill_checked(
                            "messaging",
                            {
                                "action": "send",
                                "channel": d.channel,
                                "recipient": d.recipient or "",
                                "text": d.text,
                            },
                        )
                    ),
                }
            )

        return {"ok": True, "results": results}
