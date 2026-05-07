"""TDD unit tests for config validation (core.config Pydantic models).

These tests define the expected behavior of the config validation layer
that will be implemented in Task 4. They will fail until core/config.py exists.
"""

import pytest
from pydantic import ValidationError

from core.config import (
    AppConfig,
    DNSHostConfig,
    MQTTConfig,
    NetworkConfig,
    NetworkIOConfig,
    NetworkIOFilters,
    ParserConfig,
    PingHostConfig,
    ProcessConfig,
    SensorConfig,
)

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


# --- Network and Process config models ---


class TestNetworkConfig:
    def test_valid_network_io_config(self):
        """NetworkIOConfig with all options parses correctly."""
        config = NetworkIOConfig(
            total=True,
            per_nic=True,
            rates=True,
            rates_per_nic=True,
            polling_interval=10.0,
            filters=NetworkIOFilters(include=["^eth"], exclude=["^lo$"]),
        )
        assert config.total is True
        assert config.per_nic is True
        assert config.rates is True
        assert config.polling_interval == 10.0
        assert config.filters.include == ["^eth"]
        assert config.filters.exclude == ["^lo$"]

    def test_network_io_defaults(self):
        """NetworkIOConfig uses sensible defaults."""
        config = NetworkIOConfig()
        assert config.total is True
        assert config.per_nic is False
        assert config.rates is False
        assert config.polling_interval == 5.0

    def test_network_io_invalid_polling_interval(self):
        """NetworkIOConfig rejects polling_interval <= 0."""
        with pytest.raises(ValidationError):
            NetworkIOConfig(polling_interval=0)
        with pytest.raises(ValidationError):
            NetworkIOConfig(polling_interval=-1)

    def test_valid_full_network_config(self):
        """NetworkConfig with io, ping, and dns sections parses correctly."""
        config = NetworkConfig(
            io=NetworkIOConfig(total=True, rates=True),
            ping=[PingHostConfig(host="8.8.8.8", id="google")],
            dns=[DNSHostConfig(host="google.com", id="google_dns")],
        )
        assert config.io.total is True
        assert len(config.ping) == 1
        assert config.ping[0].host == "8.8.8.8"
        assert len(config.dns) == 1
        assert config.dns[0].host == "google.com"


class TestPingHostConfig:
    def test_valid_ping_config(self):
        """PingHostConfig with all options parses correctly."""
        config = PingHostConfig(
            host="1.1.1.1",
            id="cloudflare",
            interface="eth0",
            timeout=3.0,
            size=64,
            polling_interval=15.0,
        )
        assert config.host == "1.1.1.1"
        assert config.id == "cloudflare"
        assert config.interface == "eth0"
        assert config.timeout == 3.0
        assert config.size == 64
        assert config.polling_interval == 15.0

    def test_ping_requires_host(self):
        """PingHostConfig requires the host field."""
        with pytest.raises(ValidationError) as exc_info:
            PingHostConfig()
        errors = exc_info.value.errors()
        field_names = [e["loc"][-1] for e in errors]
        assert "host" in field_names

    def test_ping_invalid_polling_interval(self):
        """PingHostConfig rejects polling_interval <= 0."""
        with pytest.raises(ValidationError):
            PingHostConfig(host="8.8.8.8", polling_interval=0)
        with pytest.raises(ValidationError):
            PingHostConfig(host="8.8.8.8", polling_interval=-5)

    def test_ping_defaults(self):
        """PingHostConfig uses correct defaults."""
        config = PingHostConfig(host="8.8.8.8")
        assert config.timeout == 5.0
        assert config.polling_interval == 30.0
        assert config.interface is None
        assert config.size is None


class TestDNSHostConfig:
    def test_valid_dns_config(self):
        """DNSHostConfig parses correctly."""
        config = DNSHostConfig(host="example.com", id="example", polling_interval=120.0)
        assert config.host == "example.com"
        assert config.id == "example"
        assert config.polling_interval == 120.0

    def test_dns_requires_host(self):
        """DNSHostConfig requires the host field."""
        with pytest.raises(ValidationError) as exc_info:
            DNSHostConfig()
        errors = exc_info.value.errors()
        field_names = [e["loc"][-1] for e in errors]
        assert "host" in field_names

    def test_dns_invalid_polling_interval(self):
        """DNSHostConfig rejects polling_interval <= 0."""
        with pytest.raises(ValidationError):
            DNSHostConfig(host="example.com", polling_interval=0)
        with pytest.raises(ValidationError):
            DNSHostConfig(host="example.com", polling_interval=-1)

    def test_dns_defaults(self):
        """DNSHostConfig uses correct defaults."""
        config = DNSHostConfig(host="example.com")
        assert config.polling_interval == 60.0
        assert config.id is None


class TestProcessConfig:
    def test_valid_process_config(self):
        """ProcessConfig parses correctly."""
        config = ProcessConfig(
            name="Firefox",
            id="firefox",
            pattern="firefox",
            polling_interval=15.0,
        )
        assert config.name == "Firefox"
        assert config.id == "firefox"
        assert config.pattern == "firefox"
        assert config.polling_interval == 15.0

    def test_process_requires_name_and_pattern(self):
        """ProcessConfig requires name and pattern fields."""
        with pytest.raises(ValidationError) as exc_info:
            ProcessConfig()
        errors = exc_info.value.errors()
        field_names = [e["loc"][-1] for e in errors]
        assert "name" in field_names
        assert "pattern" in field_names

    def test_process_invalid_polling_interval(self):
        """ProcessConfig rejects polling_interval <= 0."""
        with pytest.raises(ValidationError):
            ProcessConfig(name="Test", pattern="test", polling_interval=0)
        with pytest.raises(ValidationError):
            ProcessConfig(name="Test", pattern="test", polling_interval=-1)

    def test_process_defaults(self):
        """ProcessConfig uses correct defaults."""
        config = ProcessConfig(name="Docker", pattern="dockerd")
        assert config.polling_interval == 10.0
        assert config.id is None
