"""Unit tests for core/logging.py — JSONFormatter and EntityLogAdapter."""

import json
import logging

from core.logging import EntityLogAdapter, JSONFormatter


class TestJSONFormatter:
    """Tests for JSONFormatter output."""

    def setup_method(self):
        self.formatter = JSONFormatter()
        self.logger = logging.getLogger("test.json_formatter")
        self.logger.setLevel(logging.DEBUG)

    def _make_record(self, msg: str, level: int = logging.INFO, **kwargs) -> logging.LogRecord:
        record = self.logger.makeRecord(
            name="test.json_formatter",
            level=level,
            fn="test_file.py",
            lno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_basic_json_output(self):
        record = self._make_record("Hello world")
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.json_formatter"
        assert parsed["message"] == "Hello world"
        assert "timestamp" in parsed

    def test_entity_context_fields(self):
        record = self._make_record("Sensor updated", entity_id="cpu_usage", entity_type="sensor")
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed["entity_id"] == "cpu_usage"
        assert parsed["entity_type"] == "sensor"

    def test_no_entity_fields_when_absent(self):
        record = self._make_record("No entity context")
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert "entity_id" not in parsed
        assert "entity_type" not in parsed

    def test_exception_formatting(self):
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = self.logger.makeRecord(
            name="test.json_formatter",
            level=logging.ERROR,
            fn="test_file.py",
            lno=1,
            msg="Something broke",
            args=(),
            exc_info=exc_info,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert "exception" in parsed
        assert "ValueError: test error" in parsed["exception"]


class TestEntityLogAdapter:
    """Tests for EntityLogAdapter context injection."""

    def setup_method(self):
        self.logger = logging.getLogger("test.entity_adapter")
        self.logger.setLevel(logging.DEBUG)
        self.adapter = EntityLogAdapter(self.logger, entity_id="echo_sensor", entity_type="command_sensor")

    def test_message_prefix(self):
        # EntityLogAdapter.process() prefixes the message
        msg, kwargs = self.adapter.process("Poll complete", {})
        assert msg == "[command_sensor/echo_sensor] Poll complete"

    def test_extra_fields_injected(self):
        _, kwargs = self.adapter.process("Poll complete", {})
        assert kwargs["extra"]["entity_id"] == "echo_sensor"
        assert kwargs["extra"]["entity_type"] == "command_sensor"

    def test_json_output_with_adapter(self):
        """End-to-end: adapter + JSONFormatter produces entity fields in JSON."""
        handler = logging.Handler()
        formatter = JSONFormatter()

        # Simulate what happens when the adapter logs through a JSONFormatter
        msg, kwargs = self.adapter.process("State updated", {})
        record = self.logger.makeRecord(
            name="test.entity_adapter",
            level=logging.INFO,
            fn="test_file.py",
            lno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        # Apply extra fields as the logging framework would
        for k, v in kwargs.get("extra", {}).items():
            setattr(record, k, v)

        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["entity_id"] == "echo_sensor"
        assert parsed["entity_type"] == "command_sensor"
        assert "[command_sensor/echo_sensor]" in parsed["message"]
