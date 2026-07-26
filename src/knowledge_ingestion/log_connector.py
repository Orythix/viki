import json
from typing import Any

from viki.config.logger import viki_logger

from .connector_base import ConnectorBase


class LogConnector(ConnectorBase):
    """
    Handles parsing semi-structured JSONL log files (like usage_session.jsonl)
    to identify sequential user actions and process flows for the KG.
    """

    def __init__(self, jsonl_path: str):
        self.jsonl_path = jsonl_path

    def process(self) -> list[dict[str, Any]]:
        """Implements the ConnectorBase contract; see :meth:`process_logs`."""
        return self.process_logs()

    def process_logs(self) -> list[dict[str, Any]]:
        """
        Reads the JSONL file line by line, assuming each line is a session event
        or a sequence of events that needs to be grouped into a 'chunk'.
        For simplicity here, we treat each valid JSON object as an event chunk.
        A more advanced version would group these into full sessions.
        """
        all_chunks: list[dict[str, Any]] = []
        try:
            with open(self.jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event_data = json.loads(line)
                        # Structure the output to match the expected chunk format
                        chunk = {
                            "content": str(
                                event_data
                            ),  # Use string representation of the event for extraction
                            "metadata": {
                                "source_path": self.jsonl_path,
                                "type": "UsageLog",
                                "session_id": event_data.get("session_id", "N/A"),
                            },
                        }
                        all_chunks.append(chunk)
                    except json.JSONDecodeError:
                        viki_logger.warning(
                            "Skipping malformed JSON line in %s: %s...",
                            self.jsonl_path,
                            line[:50],
                        )
        except FileNotFoundError:
            viki_logger.error("Usage log file not found at %s", self.jsonl_path)
        return all_chunks


# ...existing code...
