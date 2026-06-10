import time
from typing import Dict, Any, List, Optional
from skills.base import BaseSkill
from config.logger import viki_logger

class MindTraceSkill(BaseSkill):
    """
    Skill for visualizing the inner workings of VIKI's cognitive architecture.
    Provides visibility into routing decisions, complexity scores, and ensemble results.
    """
    def __init__(self, controller=None):
        super().__init__()
        self._controller = controller

    @property
    def name(self) -> str:
        return "mind_trace"

    @property
    def description(self) -> str:
        return "Visualizes VIKI's cognitive trace and routing decisions. Actions: last, history."

    @property
    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["last", "history"],
                    "description": "Trace action"
                },
                "session_id": {
                    "type": "string",
                    "description": "Target session ID (optional)"
                }
            },
            "required": ["action"]
        }

    async def execute(self, params: Dict[str, Any]) -> str:
        action = params.get("action")
        session_id = params.get("session_id")
        
        if not self._controller:
            return "Error: Controller not linked to this skill."

        try:
            if action == "last":
                meta = self._controller.get_last_response_meta(session_id=session_id)
                if not meta:
                    return "No recent cognitive trace found for this session."
                
                output = [
                    f"--- VIKI Cognitive Trace (Last Turn) ---",
                    f"Model Tier:   {meta.get('model_tier', 'N/A').upper()}",
                    f"Source:       {meta.get('source', 'N/A')}",
                    f"Elapsed:      {meta.get('elapsed_ms', 0):.2f} ms",
                    f"Ensemble Used: {meta.get('use_ensemble', False)}",
                ]
                
                # Complexity Details
                if "judgment" in meta:
                    j = meta["judgment"]
                    score = j.get("complexity_score", 0)
                    output.append(f"\nComplexity Score: {score:.3f}")
                    output.append(f" - Clarity: {j.get('clarity', 0):.2f}")
                    output.append(f" - Risk:    {j.get('risk', 0):.2f}")
                    output.append(f" - Novelty: {j.get('novelty', 0):.2f}")
                    output.append(f" - Reason:  {j.get('reason', 'N/A')}")
                
                # Usage info
                usage = meta.get("usage", {})
                if usage:
                    output.append(f"\nResource Usage:")
                    output.append(f" - Input:  {usage.get('input_tokens', 0)} tokens")
                    output.append(f" - Output: {usage.get('output_tokens', 0)} tokens")
                    output.append(f" - Cost:   ${usage.get('total_cost_usd', 0):.6f}")
                
                return "\n".join(output)

            elif action == "history":
                # For history, we'd ideally pull from a tracing DB or in-memory list.
                # Since Orchestrator doesn't expose a full list yet, we'll suggest using /logs
                # or provide what we have.
                return "Full cognitive history visualization is coming in v8.2. Use /logs for detailed telemetry for now."

            return f"Error: Unknown action '{action}'"

        except Exception as e:
            viki_logger.error(f"MindTrace Execution Error: {e}")
            return f"MindTrace Error: {str(e)}"
