"""Integration tests for ReloadManager — verifies reload orchestration logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.config import (
    AppConfig,
    ButtonConfig,
    EntitiesConfig,
    HassConfig,
    MQTTConfig,
    SensorConfig,
)
from core.reload import ReloadManager, ReloadResult


def _make_config(sensors=None, buttons=None) -> AppConfig:
    """Helper to build an AppConfig with given entity lists."""
    return AppConfig(
        mqtt=MQTTConfig(),
        hass=HassConfig(device_name="Test", device_id="test"),
        entities=EntitiesConfig(
            sensors=sensors or [],
            buttons=buttons or [],
        ),
    )


@pytest.fixture
def mock_mqtt_settings():
    """Mock MQTT settings with a mock client."""
    settings = MagicMock()
    settings.client = MagicMock()
    return settings


@pytest.fixture
def mock_ha_device():
    """Mock HA device info."""
    return MagicMock()


@pytest.fixture
def reload_manager(mock_mqtt_settings, mock_ha_device, tmp_path):
    """Create a ReloadManager with a temp config path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("")
    return ReloadManager(
        config_path=str(config_file),
        mqtt_settings=mock_mqtt_settings,
        ha_device=mock_ha_device,
        ha_devices={},
        sub_devices=False,
        device_name="Test",
    )


class TestReloadManagerInvalidConfig:
    @pytest.mark.asyncio
    async def test_returns_error_on_invalid_config(self, reload_manager):
        """Invalid config returns error result without crashing."""
        current_config = _make_config(sensors=[
            SensorConfig(name="temp", command="echo 42", polling_interval=10)
        ])

        # Create a mock entity in the registry
        mock_entity = MagicMock()
        mock_entity.stop = MagicMock()
        registry = {("sensor", "temp"): mock_entity}

        with patch("core.reload.load_config") as mock_load:
            mock_load.side_effect = Exception("YAML parse error")
            # ConfigError is what load_config raises
            from core.config import ConfigError
            mock_load.side_effect = ConfigError("Invalid YAML: bad indentation")

            result = await reload_manager.reload(registry, current_config)

        assert result.success is False
        assert "Invalid YAML" in result.error
        # Entity should NOT have been stopped
        mock_entity.stop.assert_not_called()


class TestReloadManagerEntityLifecycle:
    @pytest.mark.asyncio
    async def test_stop_called_on_removed_entities(self, reload_manager):
        """Removed entities have stop() called during reload."""
        old_config = _make_config(
            sensors=[SensorConfig(name="temp", command="echo 42", polling_interval=10)]
        )
        new_config = _make_config(sensors=[])

        mock_entity = MagicMock()
        mock_entity.stop = MagicMock()
        mock_entity._ha_entity = None
        registry = {("sensor", "temp"): mock_entity}

        with patch("core.reload.load_config", return_value=new_config):
            result = await reload_manager.reload(registry, old_config)

        assert result.success is True
        mock_entity.stop.assert_called_once()
        assert "temp" in result.removed

    @pytest.mark.asyncio
    async def test_new_entities_created_for_additions(self, reload_manager, mock_mqtt_settings, mock_ha_device):
        """Added entities are created and appear in the new registry."""
        old_config = _make_config(sensors=[])
        new_config = _make_config(
            sensors=[SensorConfig(name="humidity", command="echo 60", polling_interval=10)]
        )

        registry: dict = {}

        mock_entity = MagicMock()
        with patch("core.reload.load_config", return_value=new_config), \
             patch("core.reload.factory_create_entity", return_value=mock_entity) as mock_factory:
            result = await reload_manager.reload(registry, old_config)

        assert result.success is True
        assert "humidity" in result.added
        assert ("sensor", "humidity") in result.new_entities
        mock_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_updated_entities_are_stopped_and_recreated(self, reload_manager):
        """Updated entities have old instance stopped and new instance created."""
        old_config = _make_config(
            sensors=[SensorConfig(name="temp", command="echo 42", polling_interval=10)]
        )
        new_config = _make_config(
            sensors=[SensorConfig(name="temp", command="echo 99", polling_interval=10)]
        )

        old_entity = MagicMock()
        old_entity.stop = MagicMock()
        registry = {("sensor", "temp"): old_entity}

        new_entity = MagicMock()
        with patch("core.reload.load_config", return_value=new_config), \
             patch("core.reload.factory_create_entity", return_value=new_entity):
            result = await reload_manager.reload(registry, old_config)

        assert result.success is True
        old_entity.stop.assert_called_once()
        assert "temp" in result.updated
        assert result.new_entities[("sensor", "temp")] is new_entity

    @pytest.mark.asyncio
    async def test_unchanged_entities_preserved(self, reload_manager):
        """Unchanged entities remain in the registry without being stopped."""
        sensor = SensorConfig(name="temp", command="echo 42", polling_interval=10)
        config = _make_config(sensors=[sensor])

        existing_entity = MagicMock()
        existing_entity.stop = MagicMock()
        registry = {("sensor", "temp"): existing_entity}

        with patch("core.reload.load_config", return_value=config):
            result = await reload_manager.reload(registry, config)

        assert result.success is True
        existing_entity.stop.assert_not_called()
        assert result.new_entities[("sensor", "temp")] is existing_entity

    @pytest.mark.asyncio
    async def test_entity_creation_failure_rolls_back(self, reload_manager):
        """If entity creation fails, partially created entities are stopped."""
        old_config = _make_config(sensors=[])
        new_config = _make_config(
            sensors=[SensorConfig(name="bad_sensor", command="echo fail", polling_interval=10)]
        )

        registry: dict = {}

        with patch("core.reload.load_config", return_value=new_config), \
             patch("core.reload.factory_create_entity", side_effect=RuntimeError("Creation failed")):
            result = await reload_manager.reload(registry, old_config)

        assert result.success is False
        assert "Creation failed" in result.error
