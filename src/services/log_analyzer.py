import json
from typing import Any

from viki.config.logger import viki_logger

# Assuming usage of other services like KnowledgeExtractor or a dedicated LLM client


class UsageLogAnalyzer:
    """
    Analyzes raw usage session logs to identify failure modes and ambiguous prompts.
    This service translates raw data into actionable insights for synthetic data generation.
    """

    def __init__(self, jsonl_path: str):
        self.jsonl_path = jsonl_path

    def analyze_logs(self) -> dict[str, Any]:
        """
        Reads the usage log and performs pattern analysis to generate a report.
        Returns a dictionary containing structured insights.
        """
        viki_logger.info("Analyzing logs from: %s", self.jsonl_path)
        failure_modes = {}
        ambiguous_prompts = []
        high_value_topics = {}
        total_records = 0

        try:
            with open(self.jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event_data = json.loads(line)
                        total_records += 1
                        # --- Failure Mode Identification Logic ---
                        if (
                            event_data.get("event") == "llm_inference"
                            and event_data.get("success") is False
                        ):
                            failure_type = event_data.get("error_code", "UNKNOWN_ERROR")
                            topic = self._determine_topic(event_data.get("prompt"))

                            if failure_type not in failure_modes:
                                failure_modes[failure_type] = []
                            failure_modes[failure_type].append({"topic": topic, "count": 1})

                        # --- Ambiguity Detection Logic ---
                        if event_data.get("trust_score", 1.0) < 0.7:
                            ambiguous_prompts.append(
                                {
                                    "prompt": event_data.get("prompt"),
                                    "context": event_data.get("session_context"),
                                    "low_score": event_data["trust_score"],
                                }
                            )

                        # --- Topic Tracking ---
                        topic = self._determine_topic(event_data.get("prompt"))
                        high_value_topics[topic] = high_value_topics.get(topic, 0) + 1

                    except json.JSONDecodeError:
                        continue  # Skip malformed lines
        except FileNotFoundError:
            viki_logger.error("Usage log file not found at %s", self.jsonl_path)
            return {"error": "File Not Found"}

        # Post-processing to summarize failure modes (simplified)
        summary_failures = {}
        for error, failures in failure_modes.items():
            # Group by topic for better reporting
            topic_counts = {}
            for f in failures:
                topic_counts[f["topic"]] = topic_counts.get(f["topic"], 0) + f["count"]
            summary_failures[error] = dict(topic_counts)

        return {
            "failure_modes": summary_failures,
            "ambiguous_prompts": ambiguous_prompts[:10],  # Limit output size
            "high_value_topics": high_value_topics,
            "total_records_processed": total_records,
        }

    def _determine_topic(self, prompt: str | None) -> str:
        """Simple heuristic to categorize a prompt into a domain topic."""
        if not prompt:
            # Log events are not guaranteed to carry a prompt field.
            return "General Inquiry"
        if "how do i" in prompt.lower() or "guide me through" in prompt.lower():
            return "Process/Workflow"
        elif any(k in prompt.lower() for k in ["api", "endpoint", "call"]):
            return "Tool Use/API Integration"
        elif "explain" in prompt.lower() or "what is" in prompt.lower():
            return "Concept Definition"
        else:
            return "General Inquiry"


# ...existing code...
