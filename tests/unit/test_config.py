"""TDD unit tests for config validation (core.config Pydantic models).

These tests define the expected behavior of the config validation layer
that will be implemented in Task 4. They will fail until core/config.py exists.
"""

import pytest
from pydantic import ValidationError

from core.config import AppConfig, MQTTConfig, ParserConfig, SensorConfig


# --- Valid configs ---

class TestValidConfigs:
    def test_minimal_config_passes(self):
        """Minimal valid config: just mqtt and hass sections."""
        config = AppConfig(
            mqtt={"host": "localhost", "port": 1883},
            hass={"device_name": "Test", "device_id": "test"},
        )
        assert config.mqtt.host == "localhost"
        assert config.mqtt.port == 1883

    def test_full_config_passes(self):
        """Full config with entities passes validation."""
        config = AppConfig(
            mqtt={"host": "broker.local", "port": 8883, "username": "user", "password": "pass"},
            hass={"device_name": "My PC", "device_id": "my_pc"},
            entities={
                "sensors": [
                    {
                        "name": "CPU Temp",
                        "command": "sensors | grep temp",
                        "polling_interval": 10.0,
                        "parse": [{"type": "regex", "regex": r"(\d+\.\d+)", "group": 1}, {"type": "float"}],
                    }
                ]
            },
        )
        assert config.hass.device_name == "My PC"
        assert len(config.entities.sensors) == 1
        assert config.entities.sensors[0].polling_interval == 10.0


# --- Invalid configs ---

class TestInvalidConfigs:
    def test_missing_mqtt_host_uses_default(self):
        """mqtt.host has a default of 'localhost', so omitting it is fine."""
        config = AppConfig(
            mqtt={"port": 1883},
            hass={"device_name": "Test", "device_id": "test"},
        )
        assert config.mqtt.host == "localhost"

    def test_missing_hass_fields_raises(self):
        """hass.device_name and device_id are required."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(
                mqtt={"host": "localhost"},
                hass={},
            )
        errors = exc_info.value.errors()
        field_names = [e["loc"][-1] for e in errors]
        assert "device_name" in field_names
        assert "device_id" in field_names

    def test_invalid_port_too_high(self):
        """Port > 65535 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MQTTConfig(host="localhost", port=70000)
        assert any("port" in str(e["loc"]) for e in exc_info.value.errors())

    def test_invalid_port_negative(self):
        """Port < 1 should be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MQTTConfig(host="localhost", port=-1)
        assert any("port" in str(e["loc"]) for e in exc_info.value.errors())

    def test_invalid_parser_type_rejected(self):
        """Parser type must be one of the known types."""
        with pytest.raises(ValidationError):
            ParserConfig(type="invalid_type")

    def test_polling_interval_zero_rejected(self):
        """polling_interval must be > 0."""
        with pytest.raises(ValidationError):
            SensorConfig(name="Test", polling_interval=0)

    def test_polling_interval_negative_rejected(self):
        """polling_interval must be > 0."""
        with pytest.raises(ValidationError):
            SensorConfig(name="Test", polling_interval=-5)


# --- Polling rate conversion ---

class TestPollingRateConversion:
    def test_polling_interval_takes_precedence(self):
        """When polling_interval is set, it's used directly."""
        sensor = SensorConfig(name="Test", polling_interval=15.0)
        assert sensor.get_polling_interval(default=10.0) == 15.0

    def test_polling_rate_converted_to_interval(self):
        """polling_rate (polls/sec) is converted: interval = 1/rate."""
        sensor = SensorConfig(name="Test", polling_rate=0.1)
        assert sensor.get_polling_interval(default=10.0) == pytest.approx(10.0)

    def test_default_used_when_neither_set(self):
        """Falls back to the provided default when neither field is set."""
        sensor = SensorConfig(name="Test")
        assert sensor.get_polling_interval(default=30.0) == 30.0
