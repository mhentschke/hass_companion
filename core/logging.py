"""Structured logging — JSONFormatter, EntityLogAdapter, and setup_logging.

Provides two output formats:
- text: Human-readable with optional entity context prefix
- json: Machine-parseable JSON lines for log aggregation systems
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Output fields: timestamp, level, logger, message, and optional
    entity_id/entity_type when present in the record.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include entity context if present
        entity_id = getattr(record, "entity_id", None)
        entity_type = getattr(record, "entity_type", None)
        if entity_id:
            entry["entity_id"] = entity_id
        if entity_type:
            entry["entity_type"] = entity_type

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


class EntityLogAdapter(logging.LoggerAdapter):
    """Injects entity_id and entity_type into log records.

    In text mode, prefixes messages with [entity_type/entity_id].
    In JSON mode, adds entity_id and entity_type as top-level fields.
    """

    def __init__(self, logger: logging.Logger, entity_id: str, entity_type: str):
        super().__init__(logger, {"entity_id": entity_id, "entity_type": entity_type})
        self._entity_id = entity_id
        self._entity_type = entity_type

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        """Add entity context to the log record."""
        extra = kwargs.get("extra", {})
        extra["entity_id"] = self._entity_id
        extra["entity_type"] = self._entity_type
        kwargs["extra"] = extra

        # Prefix message with entity context for text formatters
        msg = f"[{self._entity_type}/{self._entity_id}] {msg}"
        return msg, kwargs


def setup_logging(level_name: str = "INFO", format: str = "text") -> None:
    """Configure logging with the given level and format.

    Args:
        level_name: Log level (DEBUG, INFO, WARNING, ERROR).
        format: Output format — 'text' for human-readable, 'json' for structured JSON lines.
    """
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO

    # Remove existing handlers to avoid duplicates on re-init
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root.addHandler(handler)
