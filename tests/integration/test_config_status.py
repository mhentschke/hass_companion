"""Integration tests for ConfigStatusSensor — verifies state transitions and attributes."""

import pytest
from unittest.mock import MagicMock

from core.entities.config_status import ConfigStatusSensor


@pytest.fixture
def mock_ha_entity():
    """Mock HA sensor entity."""
    entity = MagicMock()
    entity.set_state = MagicMock()
    entity.set_attributes = MagicMock()
    entity.write_config = MagicMock()
    return entity


@pytest.fixture
def config_status(mock_ha_entity):
    """ConfigStatusSensor with injected mock HA entity."""
    mqtt_settings = MagicMock()
    device = MagicMock()
    sensor = ConfigStatusSensor(
        mqtt_settings, device, device_id="test_device", _ha_entity=mock_ha_entity
    )
    return sensor


class TestConfigStatusSensorStateTransitions:
    def test_initial_state_is_valid(self, config_status, mock_ha_entity):
        """Sensor starts with state 'valid' on creation."""
        # Initial publish happens in __init__
        mock_ha_entity.set_state.assert_called_with("valid")

    def test_set_error_transitions_to_error(self, config_status, mock_ha_entity):
        """set_error() transitions state to 'error' with error details."""
        config_status.set_error("Invalid YAML: bad indentation")

        mock_ha_entity.set_state.assert_called_with("error")
        attrs = mock_ha_entity.set_attributes.call_args[0][0]
        assert attrs["last_error"] == "Invalid YAML: bad indentation"
        assert attrs["last_error_time"] is not None

    def test_set_valid_after_error_clears_error(self, config_status, mock_ha_entity):
        """set_valid() after set_error() clears the error and restores 'valid'."""
        config_status.set_error("Some error")
        config_status.set_valid(added=1, removed=0, updated=0)

        mock_ha_entity.set_state.assert_called_with("valid")
        attrs = mock_ha_entity.set_attributes.call_args[0][0]
        assert attrs["last_error"] is None
        assert attrs["last_reload"] is not None
        assert attrs["entities_added"] == 1


class TestConfigStatusSensorAttributes:
    def test_set_valid_sets_counts(self, config_status, mock_ha_entity):
        """set_valid() sets entity count attributes correctly."""
        config_status.set_valid(added=3, removed=1, updated=2)

        attrs = mock_ha_entity.set_attributes.call_args[0][0]
        assert attrs["entities_added"] == 3
        assert attrs["entities_removed"] == 1
        assert attrs["entities_updated"] == 2
        assert attrs["last_reload"] is not None

    def test_set_error_preserves_last_reload(self, config_status, mock_ha_entity):
        """set_error() does not overwrite last_reload from a previous success."""
        config_status.set_valid(added=1, removed=0, updated=0)
        valid_attrs = mock_ha_entity.set_attributes.call_args[0][0]
        last_reload = valid_attrs["last_reload"]

        config_status.set_error("New error")
        error_attrs = mock_ha_entity.set_attributes.call_args[0][0]
        assert error_attrs["last_reload"] == last_reload
